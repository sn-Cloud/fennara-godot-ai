//! Private, immutable Codex runtime updates for complete Windows addons only.
use crate::{app_layout::AppLayout, release_package};
use base64::{Engine, engine::general_purpose::STANDARD};
use semver::Version;
use serde_json::{Value, json};
use sha2::{Digest, Sha512};
use std::{
    fs,
    io::{Cursor, Read},
    path::{Component, Path},
    process::Command,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

const PACKAGE: &str = "@openai/codex";
const INTERVAL: u64 = 6 * 60 * 60;

// Invoked in a background child by the bundled daemon. Failure is recorded but
// never changes the active runtime, account credentials, or upstream installation.
pub fn run() -> Result<(), String> {
    if !cfg!(all(windows, target_arch = "x86_64")) {
        return Ok(());
    }
    let layout = AppLayout::detect()?;
    let manifest: Value = serde_json::from_slice(
        &fs::read(&layout.current_manifest_path).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    if manifest.get("bundle_id").and_then(Value::as_str).is_none() {
        return Ok(());
    }
    let bundled = Path::new(
        manifest["daemon_runtime"]
            .as_str()
            .ok_or("Missing bundled daemon")?,
    )
    .parent()
    .ok_or("Invalid daemon path")?
    .join("codex");
    let bundled_version = metadata_version(&bundled)?;
    let root = layout.app_dir.join("codex-runtime");
    fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    let _lock = release_package::install_lock::acquire(&layout, "codex-runtime")?;
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let status_path = root.join("status.json");
    let previous: Value = fs::read(&status_path)
        .ok()
        .and_then(|raw| serde_json::from_slice(&raw).ok())
        .unwrap_or(Value::Null);
    if previous["checked_at"]
        .as_u64()
        .is_some_and(|last| now >= last && now - last < INTERVAL)
    {
        return Ok(());
    }
    write_json(
        &status_path,
        &json!({"checked_at": now, "state": "checking"}),
    )?;
    let result = update(&root, &bundled_version);
    match &result {
        Ok(version) => write_json(
            &status_path,
            &json!({"checked_at": now, "state": "ready", "version": version}),
        )?,
        Err(error) => write_json(
            &status_path,
            &json!({"checked_at": now, "state": "failed", "error": error}),
        )?,
    }
    result.map(|_| ())
}

// Only the official npm package and its SHA-512 integrity value may supply bytes.
// Version directories remain immutable so existing Codex processes keep running.
fn update(root: &Path, bundled: &Version) -> Result<String, String> {
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(180))
        .build();
    let latest: Value = agent
        .get("https://registry.npmjs.org/@openai%2Fcodex/latest")
        .call()
        .map_err(|e| e.to_string())?
        .into_json()
        .map_err(|e| e.to_string())?;
    let stable = Version::parse(
        latest["version"]
            .as_str()
            .ok_or("Missing latest Codex version")?,
    )
    .map_err(|e| e.to_string())?;
    if !stable.pre.is_empty() || !stable.build.is_empty() {
        return Err("Expected stable Codex release".into());
    }
    let metadata: Value = agent
        .get(&format!(
            "https://registry.npmjs.org/@openai%2Fcodex/{stable}-win32-x64"
        ))
        .call()
        .map_err(|e| e.to_string())?
        .into_json()
        .map_err(|e| e.to_string())?;
    let (version, url, integrity) = validate_metadata(&metadata)?;
    if version != stable {
        return Err("Codex registry version mismatch".into());
    }
    let active = fs::read(root.join("current.json"))
        .ok()
        .and_then(|v| serde_json::from_slice::<Value>(&v).ok());
    let active_version = active
        .as_ref()
        .and_then(|v| v["version"].as_str())
        .and_then(|v| Version::parse(v).ok())
        .filter(|v| {
            v.pre.is_empty()
                && v.build.is_empty()
                && root.join(v.to_string()).join("bin/codex.exe").is_file()
        });
    let installed = active_version
        .as_ref()
        .filter(|v| *v > bundled)
        .unwrap_or(bundled);
    if &version <= installed {
        return Ok(installed.to_string());
    }
    let mut bytes = Vec::new();
    agent
        .get(&url)
        .call()
        .map_err(|e| e.to_string())?
        .into_reader()
        .take(300 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() > 300 * 1024 * 1024 {
        return Err("Codex download exceeds size limit".into());
    }
    verify_integrity(&bytes, &integrity)?;
    let staging = root.join(format!("staging-{}-{}", version, std::process::id()));
    if staging.exists() {
        fs::remove_dir_all(&staging).map_err(|e| e.to_string())?;
    }
    fs::create_dir_all(&staging).map_err(|e| e.to_string())?;
    let result = (|| {
        unpack(&bytes, &staging).map_err(|e| format!("Extracting Codex: {e}"))?;
        let vendor = staging.join("package/vendor/x86_64-pc-windows-msvc");
        if metadata_version(&vendor)? != version {
            return Err("Codex archive version mismatch".into());
        }
        for required in [
            "bin/codex.exe",
            "codex-resources/codex-command-runner.exe",
            "codex-resources/codex-windows-sandbox-setup.exe",
        ] {
            if !vendor.join(required).is_file() {
                return Err(format!("Codex archive missing {required}"));
            }
        }
        // Windows may retain executable image handles after a process exits.
        // Finalize the immutable directory before probing, publish the pointer last.
        let destination = root.join(version.to_string());
        if destination.exists() {
            if !same_tree(&vendor, &destination)? {
                return Err("Existing Codex runtime differs from verified download".into());
            }
        } else {
            fs::rename(&vendor, &destination)
                .map_err(|e| format!("Finalizing Codex runtime: {e}"))?;
        }
        let mut command = Command::new(destination.join("bin/codex.exe"));
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        command
            .arg("--version")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null());
        let mut child = command
            .spawn()
            .map_err(|e| format!("Starting Codex validation: {e}"))?;
        let started = std::time::Instant::now();
        while child.try_wait().map_err(|e| e.to_string())?.is_none() {
            if started.elapsed() > Duration::from_secs(20) {
                let _ = child.kill();
                let _ = child.wait();
                return Err("Codex runtime validation timed out".into());
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        let output = child.wait_with_output().map_err(|e| e.to_string())?;
        if !output.status.success()
            || String::from_utf8_lossy(&output.stdout).trim() != format!("codex-cli {version}")
        {
            return Err("Codex runtime validation failed".into());
        }
        write_json(
            &root.join("current.json"),
            &json!({"version": version.to_string()}),
        )?;
        Ok(version.to_string())
    })();
    let _ = fs::remove_dir_all(&staging);
    result
}

fn metadata_version(root: &Path) -> Result<Version, String> {
    let data: Value = serde_json::from_slice(
        &fs::read(root.join("codex-package.json")).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    Version::parse(data["version"].as_str().ok_or("Missing Codex version")?)
        .map_err(|e| e.to_string())
}

fn same_tree(left: &Path, right: &Path) -> Result<bool, String> {
    let mut names = Vec::new();
    for entry in fs::read_dir(left).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        names.push(entry.file_name());
        let target = right.join(entry.file_name());
        let Ok(meta) = fs::symlink_metadata(&target) else {
            return Ok(false);
        };
        if meta.file_type().is_symlink() {
            return Ok(false);
        }
        if entry.file_type().map_err(|e| e.to_string())?.is_dir() {
            if !meta.is_dir() || !same_tree(&entry.path(), &target)? {
                return Ok(false);
            }
        } else if !meta.is_file()
            || fs::read(entry.path()).map_err(|e| e.to_string())?
                != fs::read(target).map_err(|e| e.to_string())?
        {
            return Ok(false);
        }
    }
    Ok(fs::read_dir(right).map_err(|e| e.to_string())?.count() == names.len())
}

fn validate_metadata(data: &Value) -> Result<(Version, String, String), String> {
    if data["name"] != PACKAGE {
        return Err("Unexpected Codex package".into());
    }
    let version = Version::parse(
        data["version"]
            .as_str()
            .and_then(|v| v.strip_suffix("-win32-x64"))
            .ok_or("Missing Windows Codex version")?,
    )
    .map_err(|e| e.to_string())?;
    if !version.pre.is_empty() || !version.build.is_empty() {
        return Err("Only stable Codex updates are supported".into());
    }
    let expected =
        format!("https://registry.npmjs.org/@openai/codex/-/codex-{version}-win32-x64.tgz");
    if data["dist"]["tarball"].as_str() != Some(&expected) {
        return Err("Unexpected Codex download source".into());
    }
    Ok((
        version,
        expected,
        data["dist"]["integrity"]
            .as_str()
            .ok_or("Missing Codex integrity")?
            .to_string(),
    ))
}

fn verify_integrity(bytes: &[u8], integrity: &str) -> Result<(), String> {
    let hash = integrity
        .strip_prefix("sha512-")
        .ok_or("Codex SHA-512 integrity required")?;
    let expected = STANDARD.decode(hash).map_err(|e| e.to_string())?;
    if expected != Sha512::digest(bytes).as_slice() {
        return Err("Codex integrity mismatch".into());
    }
    Ok(())
}

// Reject links, traversal, duplicate destinations and expansion bombs before activation.
fn unpack(bytes: &[u8], target: &Path) -> Result<(), String> {
    let mut archive = tar::Archive::new(flate2::read::GzDecoder::new(Cursor::new(bytes)));
    let mut size = 0u64;
    let mut seen = std::collections::HashSet::new();
    for entry in archive.entries().map_err(|e| e.to_string())? {
        let mut entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path().map_err(|e| e.to_string())?.into_owned();
        let kind = entry.header().entry_type();
        if !path.starts_with("package")
            || path
                .components()
                .any(|c| !matches!(c, Component::Normal(_)))
            || (!kind.is_file() && !kind.is_dir())
            || !seen.insert(path.clone())
        {
            return Err("Unsafe Codex archive entry".into());
        }
        size = size
            .checked_add(entry.size())
            .ok_or("Archive size overflow")?;
        if size > 1024 * 1024 * 1024 {
            return Err("Codex archive exceeds size limit".into());
        }
        if !entry
            .unpack_in(target)
            .map_err(|e| format!("{}: {e}", path.display()))?
        {
            return Err("Unsafe Codex archive path".into());
        }
    }
    Ok(())
}

fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    release_package::write_current_manifest(
        path,
        &serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    // Read-only registry access and downloads into an isolated temporary cache.
    #[test]
    #[ignore = "downloads the official Codex runtime"]
    fn live_official_runtime_update() {
        let root = crate::release_client::create_temp_dir("fennara-codex-update-test").unwrap();
        let result = update(&root, &Version::new(0, 0, 0));
        let version = result.as_ref().unwrap();
        assert!(root.join(version).join("bin/codex.exe").is_file());
        let pointer = fs::read(root.join("current.json")).unwrap();
        assert_eq!(update(&root, &Version::new(0, 0, 0)).unwrap(), *version);
        assert_eq!(pointer, fs::read(root.join("current.json")).unwrap());
        println!("Verified official runtime update and no-op recheck: {version}");
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn rejects_untrusted_source_prerelease_and_corrupt_download() {
        let mut data = json!({"name": PACKAGE,"version":"0.155.1-win32-x64","dist":{"tarball":"https://registry.npmjs.org/@openai/codex/-/codex-0.155.1-win32-x64.tgz","integrity":"sha512-test"}});
        assert!(validate_metadata(&data).is_ok());
        data["dist"]["tarball"] = json!("https://example.com/runtime.tgz");
        assert!(validate_metadata(&data).is_err());
        data["version"] = json!("0.156.0-alpha.1");
        assert!(validate_metadata(&data).is_err());
        let integrity = format!("sha512-{}", STANDARD.encode(Sha512::digest(b"good")));
        assert!(verify_integrity(b"good", &integrity).is_ok());
        assert!(verify_integrity(b"corrupt", &integrity).is_err());
    }

    #[test]
    fn archive_links_are_rejected_without_touching_active_pointer() {
        let root = crate::release_client::create_temp_dir("fennara-codex-archive-test").unwrap();
        fs::write(root.join("current.json"), b"previous selection").unwrap();
        let encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
        let mut archive = tar::Builder::new(encoder);
        let mut header = tar::Header::new_gnu();
        header.set_entry_type(tar::EntryType::Symlink);
        header.set_size(0);
        archive
            .append_link(&mut header, "package/link", "../../current.json")
            .unwrap();
        let bytes = archive.into_inner().unwrap().finish().unwrap();
        assert!(unpack(&bytes, &root.join("staging")).is_err());
        assert_eq!(
            fs::read(root.join("current.json")).unwrap(),
            b"previous selection"
        );
        fs::remove_dir_all(root).unwrap();
    }
}
