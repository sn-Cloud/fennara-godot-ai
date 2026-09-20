//! Offline setup for the complete Windows addon. Only verified bundle files are
//! activated; a different running build must be idle before it can be replaced.
use crate::{
    app_layout::{AppLayout, read_current_manifest},
    daemon_setup,
    operation::{self, Phase},
    project_install, release_package,
};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path},
};

#[derive(Deserialize)]
struct Bundle {
    version: String,
    platform: String,
    files: BTreeMap<String, String>,
}

// Called by the Godot setup button. Resolve the bundle from the selected project,
// never from an online release or an unrelated installed addon.
pub fn run(args: Vec<&str>) -> Result<(), String> {
    if !cfg!(target_os = "windows") {
        return Err("The bundled addon currently supports Windows x86_64 only".into());
    }
    let mut project = None;
    let mut index = 0;
    while index < args.len() {
        match args[index] {
            "--project" | "--operation-id" => {
                let value = args.get(index + 1).ok_or("missing setup argument")?;
                if args[index] == "--project" {
                    project = Some(*value);
                }
                index += 2;
            }
            other => return Err(format!("unknown bundled setup option: {other}")),
        }
    }
    let project = Path::new(project.ok_or("--project is required")?);
    project_install::ensure_godot_project(project)?;
    let addon = project.join("addons/fennara");
    let source = addon.join("local/windows-x86_64");
    let raw = fs::read(source.join("bundle.json")).map_err(|e| e.to_string())?;
    let version = fs::read_to_string(addon.join("VERSION")).map_err(|e| e.to_string())?;
    if version.trim() != env!("CARGO_PKG_VERSION") {
        return Err("Bundled installer version mismatch".into());
    }
    operation::phase(Phase::Verifying, "Checking the bundled Fennara files")?;
    let bundle = verify_bundle(&source, &raw, version.trim())?;
    operation::set_requested_version(&bundle.version)?;
    let id = format!("{:x}", Sha256::digest(&raw));
    let layout = AppLayout::detect()?;
    layout.ensure_base_dirs()?;
    let _lock = release_package::install_lock::acquire(&layout, "bundled-activation")?;
    let current = read_current_manifest(&layout.current_manifest_path)?;
    let runtime = layout.versions_dir.join(format!("bundled-{id}"));
    if current.as_ref().and_then(|v| v["bundle_id"].as_str()) == Some(id.as_str())
        && verify_bundle(&runtime, &raw, &bundle.version).is_ok()
        && ["fennara.exe", "fennara-daemon.exe", "fennara-mcp.exe"]
            .iter()
            .all(|name| layout.bin_dir.join(name).is_file())
    {
        daemon_setup::ensure_running(&layout, &bundle.version)?;
        return Ok(());
    }
    daemon_setup::ensure_switch_available(&layout, None)?;
    daemon_setup::shutdown_if_running(&layout)?;
    operation::phase(Phase::Staging, "Preparing the bundled Fennara runtime")?;
    fs::create_dir_all(&runtime).map_err(|e| e.to_string())?;
    for name in bundle.files.keys() {
        let target = runtime.join(name);
        fs::create_dir_all(target.parent().unwrap()).map_err(|e| e.to_string())?;
        fs::copy(source.join(name), &target).map_err(|e| format!("copy {name}: {e}"))?;
    }
    // Verify the copied bytes before changing any active paths.
    verify_bundle(&runtime, &raw, &bundle.version)?;
    for name in ["fennara.exe", "fennara-daemon.exe", "fennara-mcp.exe"] {
        replace_launcher(&runtime.join(name), &layout.bin_dir.join(name))?;
    }
    let previous = fs::read(&layout.current_manifest_path).ok();
    let manifest = serde_json::json!({
        "version": bundle.version,
        "bundle_id": id,
        "daemon_runtime": runtime.join("fennara-daemon-runtime.exe"),
        "mcp_runtime": runtime.join("fennara-mcp-runtime.exe"),
        "addon": fs::canonicalize(&addon).map_err(|e| e.to_string())?,
    });
    release_package::write_current_manifest(
        &layout.current_manifest_path,
        &serde_json::to_vec_pretty(&manifest).map_err(|e| e.to_string())?,
    )?;
    operation::phase(Phase::Validating, "Starting Fennara")?;
    if let Err(error) = daemon_setup::ensure_running(&layout, &bundle.version) {
        // Retain the prior selection when startup fails; report both failures.
        if let Err(restore) = release_package::restore_manifest(previous.as_deref()) {
            return Err(format!(
                "{error}; restoring previous runtime failed: {restore}"
            ));
        }
        return Err(error);
    }
    Ok(())
}

// Validate manifest paths and hashes before setup writes anything. Hashes identify
// exact builds, including two fork builds with the same semantic version.
fn verify_bundle(source: &Path, raw: &[u8], version: &str) -> Result<Bundle, String> {
    let bundle: Bundle = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
    if bundle.version != version || bundle.platform != "windows-x86_64" {
        return Err("The bundled runtime does not match this addon/platform".into());
    }
    for required in [
        "fennara.exe",
        "fennara-daemon.exe",
        "fennara-daemon-runtime.exe",
        "fennara-mcp.exe",
        "fennara-mcp-runtime.exe",
        "codex/bin/codex.exe",
        "codex/codex-resources/codex-command-runner.exe",
        "codex/codex-resources/codex-windows-sandbox-setup.exe",
    ] {
        if !bundle.files.contains_key(required) {
            return Err(format!("Bundle is missing {required}"));
        }
    }
    for (name, expected) in &bundle.files {
        if name.is_empty()
            || name.contains('\\')
            || name.contains(':')
            || !Path::new(name)
                .components()
                .all(|c| matches!(c, Component::Normal(_)))
        {
            return Err(format!("Invalid bundle file path: {name}"));
        }
        let bytes = fs::read(source.join(name)).map_err(|e| format!("read {name}: {e}"))?;
        if format!("{:x}", Sha256::digest(&bytes)) != *expected {
            return Err(format!("Bundle file checksum mismatch: {name}"));
        }
    }
    Ok(bundle)
}

// Validate a future fork package with its own declared version before staging it.
pub(crate) fn verify_addon(addon: &Path, version: &str) -> Result<(), String> {
    let root = addon.join("local/windows-x86_64");
    let raw = fs::read(root.join("bundle.json")).map_err(|e| e.to_string())?;
    verify_bundle(&root, &raw, version).map(|_| ())
}

// Replace small shared launchers through a temporary file. A locked executable
// fails with an actionable error rather than leaving a partially copied launcher.
fn replace_launcher(source: &Path, target: &Path) -> Result<(), String> {
    let next = target.with_extension("exe.bundled-next");
    let backup = target.with_extension("exe.bundled-previous");
    fs::copy(source, &next).map_err(|e| e.to_string())?;
    if backup.exists() {
        fs::remove_file(&backup).map_err(|e| e.to_string())?;
    }
    if target.exists() {
        fs::rename(target, &backup)
            .map_err(|e| format!("Close running Fennara command-line clients and retry: {e}"))?;
    }
    if let Err(error) = fs::rename(&next, target) {
        if backup.exists() {
            let _ = fs::rename(&backup, target);
        }
        return Err(error.to_string());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn verifies_bytes_and_rejects_corruption_and_path_traversal() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../temp/bundle-verification");
        let root = root.join(format!("{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let mut files = BTreeMap::new();
        for name in [
            "fennara.exe",
            "fennara-daemon.exe",
            "fennara-daemon-runtime.exe",
            "fennara-mcp.exe",
            "fennara-mcp-runtime.exe",
            "codex/bin/codex.exe",
            "codex/codex-resources/codex-command-runner.exe",
            "codex/codex-resources/codex-windows-sandbox-setup.exe",
        ] {
            let target = root.join(name);
            fs::create_dir_all(target.parent().unwrap()).unwrap();
            fs::write(target, name).unwrap();
            files.insert(name, format!("{:x}", Sha256::digest(name.as_bytes())));
        }
        let mut value = serde_json::json!({"version": env!("CARGO_PKG_VERSION"), "platform": "windows-x86_64", "files": files});
        let raw = serde_json::to_vec(&value).unwrap();
        assert!(verify_bundle(&root, &raw, env!("CARGO_PKG_VERSION")).is_ok());
        fs::write(root.join("fennara.exe"), "corrupt").unwrap();
        assert!(
            verify_bundle(&root, &raw, env!("CARGO_PKG_VERSION"))
                .err()
                .unwrap()
                .contains("checksum")
        );
        value["files"]["../escape.exe"] = serde_json::json!("unused");
        assert!(
            verify_bundle(
                &root,
                &serde_json::to_vec(&value).unwrap(),
                env!("CARGO_PKG_VERSION")
            )
            .err()
            .unwrap()
            .contains("Invalid bundle file path")
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rejects_incomplete_and_wrong_version_bundles_before_activation() {
        let raw = serde_json::json!({"version": env!("CARGO_PKG_VERSION"), "platform": "windows-x86_64", "files": {}});
        assert!(
            verify_bundle(
                Path::new("."),
                &serde_json::to_vec(&raw).unwrap(),
                env!("CARGO_PKG_VERSION")
            )
            .err()
            .unwrap()
            .contains("missing")
        );
        assert!(
            verify_bundle(Path::new("."), &serde_json::to_vec(&raw).unwrap(), "0.0.0").is_err()
        );
    }
}
