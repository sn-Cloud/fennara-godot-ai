//! Complete-addon updates are isolated from the upstream release client.
use crate::{
    app_layout::AppLayout,
    bundled_install, daemon_setup,
    operation::{self, Phase},
    release_client,
    release_package::InstalledPackage,
    update_stage,
};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Cursor, Read},
    path::{Component, Path},
    process::Command,
};

const REPOSITORY: &str = "sn-Cloud/fennara-godot-ai";

// Download a fork-only archive while Godot stays open; use the existing staged
// transaction/rollback flow for application after the editor confirms shutdown.
pub(crate) fn prepare(
    project: &Path,
    current: &str,
    request: &str,
    prepare_only: bool,
    godot: Option<(u32, u64, &Path)>,
) -> Result<(), String> {
    if !prepare_only {
        return Err(
            "Complete addons update through Godot's update panel (or update --prepare).".into(),
        );
    }
    let selector = if request.is_empty() || request == "latest" {
        "latest".to_string()
    } else {
        let version = stable_version(request)?;
        format!("tags/v{version}")
    };
    let raw = release_client::download_bytes(
        &format!("https://api.github.com/repos/{REPOSITORY}/releases/{selector}"),
        "fork release metadata",
    )?;
    let release: Value = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    let (version, url, hash) = release_asset(&release)?;
    if stable_version(&version)? <= stable_version(current)? {
        return Ok(());
    }
    operation::set_requested_version(&version)?;
    daemon_setup::ensure_switch_available(&AppLayout::detect()?, Some(project))?;
    let bytes = release_client::download_bytes(&url, "complete fork addon")?;
    if format!("{:x}", Sha256::digest(&bytes)) != hash {
        return Err("Fork addon SHA-256 mismatch".into());
    }
    let temporary = release_client::create_temp_dir("fennara-fork-update")?;
    let result = (|| {
        extract_addon(&bytes, &temporary)?;
        let addon = temporary.join("addons/fennara");
        bundled_install::verify_addon(&addon, &version)?;
        let id = operation::current_id().ok_or("Missing update operation ID")?;
        update_stage::prepare(
            project,
            current,
            &InstalledPackage {
                version,
                addon_dir: addon,
            },
            &id,
            godot,
        )?;
        operation::phase(
            Phase::ReadyToClose,
            "The verified fork update is ready; close Godot to install",
        )?;
        operation::defer_completion()
    })();
    let _ = fs::remove_dir_all(&temporary);
    result
}

fn stable_version(value: &str) -> Result<semver::Version, String> {
    let parsed =
        semver::Version::parse(value.trim_start_matches('v')).map_err(|e| e.to_string())?;
    if !parsed.pre.is_empty() || !parsed.build.is_empty() {
        return Err("Fork updater requires a stable version".into());
    }
    Ok(parsed)
}

// GitHub computes the SHA-256 digest when the maintainer uploads the release asset.
// Never accept an upstream/source-only archive or a URL outside the fork release.
fn release_asset(release: &Value) -> Result<(String, String, String), String> {
    if release["draft"] != false || release["prerelease"] != false {
        return Err("Expected published stable fork release".into());
    }
    let version = stable_version(
        release["tag_name"]
            .as_str()
            .ok_or("Missing fork release tag")?,
    )?
    .to_string();
    let name = format!("fennara-addon-windows-x86_64-standalone-v{version}.zip");
    let expected = format!("https://github.com/{REPOSITORY}/releases/download/v{version}/{name}");
    let asset = release["assets"]
        .as_array()
        .and_then(|a| a.iter().find(|v| v["name"] == name))
        .ok_or("This fork release has no complete Windows addon")?;
    if asset["browser_download_url"].as_str() != Some(&expected) {
        return Err("Unexpected fork download source".into());
    }
    let hash = asset["digest"]
        .as_str()
        .and_then(|v| {
            v.strip_prefix("sha256-")
                .or_else(|| v.strip_prefix("sha256:"))
        })
        .ok_or("Fork asset has no SHA-256 digest")?;
    if hash.len() != 64
        || !hash
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    {
        return Err("Invalid fork asset digest".into());
    }
    Ok((version, expected, hash.to_string()))
}

fn extract_addon(bytes: &[u8], target: &Path) -> Result<(), String> {
    let mut zip = zip::ZipArchive::new(Cursor::new(bytes)).map_err(|e| e.to_string())?;
    let mut total = 0u64;
    let mut seen = std::collections::HashSet::new();
    for index in 0..zip.len() {
        let mut entry = zip.by_index(index).map_err(|e| e.to_string())?;
        let path = entry.enclosed_name().ok_or("Unsafe addon archive path")?;
        if path
            .components()
            .any(|c| !matches!(c, Component::Normal(_)))
            || !(path == Path::new("addons") || path.starts_with("addons/fennara"))
            || entry.unix_mode().is_some_and(|m| {
                m & 0o170000 != 0 && m & 0o170000 != 0o100000 && m & 0o170000 != 0o040000
            })
            || !seen.insert(path.to_string_lossy().to_lowercase())
        {
            return Err("Unsafe addon archive entry".into());
        }
        total = total
            .checked_add(entry.size())
            .ok_or("Addon size overflow")?;
        if total > 2 * 1024 * 1024 * 1024 {
            return Err("Addon archive exceeds size limit".into());
        }
        let destination = target.join(path);
        if entry.is_dir() {
            fs::create_dir_all(destination).map_err(|e| e.to_string())?;
        } else {
            fs::create_dir_all(destination.parent().ok_or("Missing addon parent")?)
                .map_err(|e| e.to_string())?;
            let mut file = fs::File::create(destination).map_err(|e| e.to_string())?;
            std::io::copy(&mut entry.by_ref(), &mut file).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

// The future package's own installer understands its runtime schema and version.
// Called only after the staged addon is verified and Godot has exited.
pub(crate) fn activate(project: &Path) -> Result<(), String> {
    let executable = project.join("addons/fennara/local/windows-x86_64/fennara.exe");
    let mut command = Command::new(executable);
    command.args(["install-bundled", "--project"]).arg(project);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let status = command.status().map_err(|e| e.to_string())?;
    if !status.success() {
        return Err(format!("Fork runtime activation failed: {status}"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn archive_extraction_is_scoped_to_the_addon() {
        use std::io::Write;
        for (name, allowed) in [
            ("addons/fennara/VERSION", true),
            ("../escape", false),
            ("project.godot", false),
            ("addons/other/plugin.cfg", false),
        ] {
            let root = release_client::create_temp_dir("fennara-fork-archive-test").unwrap();
            let mut archive = zip::ZipWriter::new(Cursor::new(Vec::new()));
            archive
                .start_file(name, zip::write::SimpleFileOptions::default())
                .unwrap();
            archive.write_all(b"test").unwrap();
            let bytes = archive.finish().unwrap().into_inner();
            assert_eq!(extract_addon(&bytes, &root).is_ok(), allowed, "{name}");
            fs::remove_dir_all(root).unwrap();
        }
    }
    #[test]
    fn fork_release_cannot_redirect_to_upstream_or_unverified_assets() {
        let name = "fennara-addon-windows-x86_64-standalone-v0.4.4.zip";
        let mut release = serde_json::json!({"draft":false,"prerelease":false,"tag_name":"v0.4.4","assets":[{"name":name,"browser_download_url":format!("https://github.com/{REPOSITORY}/releases/download/v0.4.4/{name}"),"digest":format!("sha256:{}", "a".repeat(64))}]});
        assert!(release_asset(&release).is_ok());
        release["assets"][0]["browser_download_url"] = serde_json::json!(format!(
            "https://github.com/fennaraOfficial/fennara-godot-ai/releases/download/v0.4.4/{name}"
        ));
        assert!(release_asset(&release).is_err());
        release["assets"] = serde_json::json!([]);
        assert!(release_asset(&release).is_err());
    }
}
