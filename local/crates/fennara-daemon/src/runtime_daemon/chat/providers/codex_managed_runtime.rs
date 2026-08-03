use std::{
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    sync::{Arc, Mutex, OnceLock},
    time::SystemTime,
};

use futures_util::StreamExt;
use serde::Serialize;
use sha2::{Digest, Sha256};
use tokio::{
    fs as async_fs,
    io::AsyncWriteExt,
    sync::{RwLock, oneshot},
};

use super::codex_runtime::PINNED_CODEX_VERSION;
use crate::runtime_daemon::chat::settings;

const WINDOWS_X64_ASSET_NAME: &str = "codex-x86_64-pc-windows-msvc.exe";
const WINDOWS_X64_ASSET_URL: &str =
    "https://releases.openai.com/codex/releases/0.144.4/codex-x86_64-pc-windows-msvc.exe";
const WINDOWS_X64_SHA256: &str = "51398051c2332b6afe08dc3b9dbb4056085c197f35ca57a307ee303d450cada5";
const DOWNLOAD_FILE_NAME: &str = "codex.exe.download";
const BACKUP_FILE_NAME: &str = "codex.exe.previous";
const HASH_BUFFER_BYTES: usize = 1024 * 1024;

#[derive(Clone, Debug, Serialize)]
pub(crate) struct ManagedCodexRuntimeStatus {
    pub(crate) supported: bool,
    pub(crate) installed: bool,
    pub(crate) installing: bool,
    pub(crate) repair_required: bool,
    pub(crate) version: &'static str,
    pub(crate) asset_name: Option<&'static str>,
    pub(crate) downloaded_bytes: u64,
    pub(crate) total_bytes: Option<u64>,
    pub(crate) executable: Option<String>,
    pub(crate) error: Option<String>,
}

#[derive(Clone, Debug)]
struct ManagedRuntimeState {
    installing: bool,
    downloaded_bytes: u64,
    total_bytes: Option<u64>,
    error: Option<String>,
}

impl Default for ManagedRuntimeState {
    fn default() -> Self {
        Self {
            installing: false,
            downloaded_bytes: 0,
            total_bytes: None,
            error: None,
        }
    }
}

struct ActiveInstall {
    cancel: oneshot::Sender<()>,
}

#[derive(Clone, Debug)]
struct VerificationCache {
    path: PathBuf,
    len: u64,
    modified: Option<SystemTime>,
    valid: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum RuntimeInspection {
    Missing,
    Valid,
    Corrupt,
}

#[derive(Debug)]
enum DownloadError {
    Cancelled,
    Failed(String),
}

static STATE: OnceLock<Arc<RwLock<ManagedRuntimeState>>> = OnceLock::new();
static ACTIVE_INSTALL: OnceLock<Mutex<Option<ActiveInstall>>> = OnceLock::new();
static VERIFICATION_CACHE: OnceLock<Mutex<Option<VerificationCache>>> = OnceLock::new();

fn state() -> &'static Arc<RwLock<ManagedRuntimeState>> {
    STATE.get_or_init(|| Arc::new(RwLock::new(ManagedRuntimeState::default())))
}

fn active_install() -> &'static Mutex<Option<ActiveInstall>> {
    ACTIVE_INSTALL.get_or_init(|| Mutex::new(None))
}

fn verification_cache() -> &'static Mutex<Option<VerificationCache>> {
    VERIFICATION_CACHE.get_or_init(|| Mutex::new(None))
}

pub(crate) fn install_supported() -> bool {
    cfg!(all(windows, target_arch = "x86_64"))
}

pub(crate) fn verified_executable() -> Option<PathBuf> {
    if !install_supported() {
        return None;
    }
    let executable = executable_path();
    matches!(
        inspect_runtime_cached(&executable),
        RuntimeInspection::Valid
    )
    .then_some(executable)
}

pub(crate) async fn status() -> ManagedCodexRuntimeStatus {
    let snapshot = state().read().await.clone();
    let executable = executable_path();
    let inspection = if install_supported() {
        let path = executable.clone();
        tokio::task::spawn_blocking(move || inspect_runtime_cached(&path))
            .await
            .unwrap_or(RuntimeInspection::Corrupt)
    } else {
        RuntimeInspection::Missing
    };
    ManagedCodexRuntimeStatus {
        supported: install_supported(),
        installed: inspection == RuntimeInspection::Valid,
        installing: snapshot.installing,
        repair_required: inspection == RuntimeInspection::Corrupt,
        version: PINNED_CODEX_VERSION,
        asset_name: install_supported().then_some(WINDOWS_X64_ASSET_NAME),
        downloaded_bytes: snapshot.downloaded_bytes,
        total_bytes: snapshot.total_bytes,
        executable: (inspection != RuntimeInspection::Missing)
            .then(|| executable.display().to_string()),
        error: snapshot.error,
    }
}

pub(crate) async fn start_install() -> Result<ManagedCodexRuntimeStatus, String> {
    if !install_supported() {
        return Err(
            "Automatic Codex runtime installation is currently available only on Windows x86_64."
                .to_string(),
        );
    }

    let (cancel_tx, cancel_rx) = oneshot::channel();
    let reserved = {
        let mut active = active_install()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if active.is_none() {
            *active = Some(ActiveInstall { cancel: cancel_tx });
            true
        } else {
            false
        }
    };
    if !reserved {
        return Err("A Codex runtime installation is already in progress.".to_string());
    }

    {
        let mut current = state().write().await;
        current.installing = true;
        current.downloaded_bytes = 0;
        current.total_bytes = None;
        current.error = None;
    }

    tokio::spawn(async move {
        let outcome = install_windows_runtime(cancel_rx).await;
        {
            let mut active = active_install()
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            *active = None;
        }
        let mut current = state().write().await;
        current.installing = false;
        match outcome {
            Ok(()) => {
                current.downloaded_bytes = current.total_bytes.unwrap_or(current.downloaded_bytes);
                current.error = None;
            }
            Err(DownloadError::Cancelled) => {
                current.error = Some("Codex runtime installation cancelled.".to_string());
            }
            Err(DownloadError::Failed(error)) => {
                current.error = Some(error);
            }
        }
    });

    Ok(status().await)
}

pub(crate) async fn cancel_install() -> Result<ManagedCodexRuntimeStatus, String> {
    let active = active_install()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .take()
        .ok_or_else(|| "No Codex runtime installation is in progress.".to_string())?;
    let _ = active.cancel.send(());
    {
        let mut current = state().write().await;
        current.installing = false;
        current.error = Some("Codex runtime installation cancelled.".to_string());
    }
    Ok(status().await)
}

async fn install_windows_runtime(cancel_rx: oneshot::Receiver<()>) -> Result<(), DownloadError> {
    let directory = version_directory();
    async_fs::create_dir_all(&directory)
        .await
        .map_err(|error| {
            DownloadError::Failed(format!("Could not create Codex runtime directory: {error}"))
        })?;
    recover_interrupted_install(&directory).map_err(|error| {
        DownloadError::Failed(format!(
            "Could not recover an interrupted Codex install: {error}"
        ))
    })?;

    let partial = directory.join(DOWNLOAD_FILE_NAME);
    let final_path = directory.join("codex.exe");
    let client = reqwest::Client::builder()
        .user_agent(format!(
            "fennara/{} codex-runtime-installer",
            env!("CARGO_PKG_VERSION")
        ))
        .build()
        .map_err(|error| {
            DownloadError::Failed(format!("Could not create Codex download client: {error}"))
        })?;

    let result = download_asset(
        &client,
        WINDOWS_X64_ASSET_URL,
        WINDOWS_X64_SHA256,
        &partial,
        cancel_rx,
        |downloaded, total| async move {
            let mut current = state().write().await;
            current.downloaded_bytes = downloaded;
            current.total_bytes = total;
        },
    )
    .await;

    if let Err(error) = result {
        let _ = async_fs::remove_file(&partial).await;
        return Err(error);
    }

    finalize_download(&partial, &final_path).map_err(|error| {
        DownloadError::Failed(format!("Could not activate the Codex runtime: {error}"))
    })?;
    invalidate_verification_cache();
    if inspect_runtime_cached(&final_path) != RuntimeInspection::Valid {
        return Err(DownloadError::Failed(
            "The installed Codex runtime failed its final SHA-256 verification.".to_string(),
        ));
    }
    Ok(())
}

async fn download_asset<F, Fut>(
    client: &reqwest::Client,
    url: &str,
    expected_sha256: &str,
    partial: &Path,
    mut cancel_rx: oneshot::Receiver<()>,
    mut on_progress: F,
) -> Result<(), DownloadError>
where
    F: FnMut(u64, Option<u64>) -> Fut,
    Fut: std::future::Future<Output = ()>,
{
    let response = client
        .get(url)
        .send()
        .await
        .map_err(|error| DownloadError::Failed(format!("Codex runtime download failed: {error}")))?
        .error_for_status()
        .map_err(|error| {
            DownloadError::Failed(format!("Codex runtime download failed: {error}"))
        })?;
    let total = response.content_length();
    let mut stream = response.bytes_stream();
    let mut file = async_fs::File::create(partial).await.map_err(|error| {
        DownloadError::Failed(format!("Could not create Codex download file: {error}"))
    })?;
    let mut hasher = Sha256::new();
    let mut downloaded = 0u64;
    on_progress(downloaded, total).await;

    loop {
        tokio::select! {
            _ = &mut cancel_rx => {
                drop(file);
                let _ = async_fs::remove_file(partial).await;
                return Err(DownloadError::Cancelled);
            }
            next = stream.next() => {
                let Some(next) = next else { break; };
                let bytes = next.map_err(|error| {
                    DownloadError::Failed(format!("Codex runtime download was interrupted: {error}"))
                })?;
                file.write_all(&bytes)
                    .await
                    .map_err(|error| DownloadError::Failed(format!("Could not write Codex runtime download: {error}")))?;
                hasher.update(&bytes);
                downloaded = downloaded.saturating_add(bytes.len() as u64);
                on_progress(downloaded, total).await;
            }
        }
    }

    file.flush().await.map_err(|error| {
        DownloadError::Failed(format!("Could not flush Codex runtime download: {error}"))
    })?;
    file.sync_all().await.map_err(|error| {
        DownloadError::Failed(format!("Could not sync Codex runtime download: {error}"))
    })?;
    drop(file);

    let actual = format!("{:x}", hasher.finalize());
    if !actual.eq_ignore_ascii_case(expected_sha256) {
        let _ = async_fs::remove_file(partial).await;
        return Err(DownloadError::Failed(format!(
            "Codex runtime checksum mismatch: expected {expected_sha256}, received {actual}."
        )));
    }
    Ok(())
}

fn finalize_download(partial: &Path, final_path: &Path) -> Result<(), String> {
    let directory = final_path
        .parent()
        .ok_or_else(|| "Codex runtime path has no parent directory.".to_string())?;
    let backup = directory.join(BACKUP_FILE_NAME);
    if backup.exists() {
        fs::remove_file(&backup).map_err(|error| error.to_string())?;
    }
    if final_path.exists() {
        fs::rename(final_path, &backup).map_err(|error| error.to_string())?;
    }
    if let Err(error) = fs::rename(partial, final_path) {
        if backup.exists() && !final_path.exists() {
            let _ = fs::rename(&backup, final_path);
        }
        return Err(error.to_string());
    }
    if backup.exists() {
        let _ = fs::remove_file(backup);
    }
    Ok(())
}

fn recover_interrupted_install(directory: &Path) -> Result<(), String> {
    fs::create_dir_all(directory).map_err(|error| error.to_string())?;
    let partial = directory.join(DOWNLOAD_FILE_NAME);
    let final_path = directory.join("codex.exe");
    let backup = directory.join(BACKUP_FILE_NAME);
    if partial.exists() {
        fs::remove_file(&partial).map_err(|error| error.to_string())?;
    }
    if backup.exists() {
        if final_path.exists() {
            fs::remove_file(&backup).map_err(|error| error.to_string())?;
        } else {
            fs::rename(&backup, &final_path).map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

fn inspect_runtime_cached(path: &Path) -> RuntimeInspection {
    let Ok(metadata) = fs::metadata(path) else {
        return RuntimeInspection::Missing;
    };
    if !metadata.is_file() {
        return RuntimeInspection::Corrupt;
    }
    let modified = metadata.modified().ok();
    let len = metadata.len();
    {
        let cache = verification_cache()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(cache) = cache
            .as_ref()
            .filter(|cache| cache.path == path && cache.len == len && cache.modified == modified)
        {
            return if cache.valid {
                RuntimeInspection::Valid
            } else {
                RuntimeInspection::Corrupt
            };
        }
    }
    let valid = sha256_file(path)
        .map(|digest| digest.eq_ignore_ascii_case(WINDOWS_X64_SHA256))
        .unwrap_or(false);
    *verification_cache()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(VerificationCache {
        path: path.to_path_buf(),
        len,
        modified,
        valid,
    });
    if valid {
        RuntimeInspection::Valid
    } else {
        RuntimeInspection::Corrupt
    }
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    let mut buffer = vec![0u8; HASH_BUFFER_BYTES];
    loop {
        let read = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn invalidate_verification_cache() {
    *verification_cache()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner()) = None;
}

fn executable_path() -> PathBuf {
    version_directory().join("codex.exe")
}

fn version_directory() -> PathBuf {
    settings::app_dir()
        .join("codex-runtime")
        .join("releases")
        .join(PINNED_CODEX_VERSION)
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64, Ordering};

    use axum::{Router, body::Body, response::Response, routing::get};
    use tokio::{net::TcpListener, time::Duration};

    use super::*;

    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    fn test_dir(name: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "fennara-codex-runtime-{name}-{}-{}",
            std::process::id(),
            TEST_COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn digest(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }

    async fn serve(body: Vec<u8>) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = Router::new().route(
            "/runtime",
            get(move || {
                let body = body.clone();
                async move { Response::new(Body::from(body)) }
            }),
        );
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        format!("http://{address}/runtime")
    }

    async fn serve_slow(first: Vec<u8>, second: Vec<u8>) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = Router::new().route(
            "/runtime",
            get(move || {
                let first = first.clone();
                let second = second.clone();
                async move {
                    let stream = futures_util::stream::unfold(0u8, move |state| {
                        let first = first.clone();
                        let second = second.clone();
                        async move {
                            match state {
                                0 => Some((Ok::<_, std::convert::Infallible>(first), 1)),
                                1 => {
                                    tokio::time::sleep(Duration::from_secs(5)).await;
                                    Some((Ok::<_, std::convert::Infallible>(second), 2))
                                }
                                _ => None,
                            }
                        }
                    });
                    Response::new(Body::from_stream(stream))
                }
            }),
        );
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        format!("http://{address}/runtime")
    }

    #[tokio::test]
    async fn download_verifies_checksum_and_writes_partial() {
        let root = test_dir("success");
        let partial = root.join("runtime.download");
        let bytes = b"verified codex runtime".to_vec();
        let url = serve(bytes.clone()).await;
        let (_cancel_tx, cancel_rx) = oneshot::channel();
        download_asset(
            &reqwest::Client::new(),
            &url,
            &digest(&bytes),
            &partial,
            cancel_rx,
            |_, _| async {},
        )
        .await
        .unwrap();
        assert_eq!(fs::read(&partial).unwrap(), bytes);
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn checksum_mismatch_removes_partial_download() {
        let root = test_dir("checksum");
        let partial = root.join("runtime.download");
        let url = serve(b"corrupt".to_vec()).await;
        let (_cancel_tx, cancel_rx) = oneshot::channel();
        let result = download_asset(
            &reqwest::Client::new(),
            &url,
            &digest(b"expected"),
            &partial,
            cancel_rx,
            |_, _| async {},
        )
        .await;
        assert!(matches!(result, Err(DownloadError::Failed(_))));
        assert!(!partial.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn cancellation_removes_partial_download() {
        let root = test_dir("cancel");
        let partial = root.join("runtime.download");
        let first = vec![1u8; 1024];
        let second = vec![2u8; 1024];
        let url = serve_slow(first.clone(), second.clone()).await;
        let expected = [first, second].concat();
        let (cancel_tx, cancel_rx) = oneshot::channel();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(100)).await;
            let _ = cancel_tx.send(());
        });
        let task = tokio::spawn({
            let partial = partial.clone();
            async move {
                download_asset(
                    &reqwest::Client::new(),
                    &url,
                    &digest(&expected),
                    &partial,
                    cancel_rx,
                    |_, _| async {},
                )
                .await
            }
        });
        assert!(matches!(task.await.unwrap(), Err(DownloadError::Cancelled)));
        assert!(!partial.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn interrupted_activation_restores_previous_runtime() {
        let root = test_dir("recover");
        let backup = root.join(BACKUP_FILE_NAME);
        let final_path = root.join("codex.exe");
        let partial = root.join(DOWNLOAD_FILE_NAME);
        fs::write(&backup, b"previous").unwrap();
        fs::write(&partial, b"partial").unwrap();
        recover_interrupted_install(&root).unwrap();
        assert_eq!(fs::read(final_path).unwrap(), b"previous");
        assert!(!backup.exists());
        assert!(!partial.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn finalize_download_replaces_existing_runtime_and_removes_backup() {
        let root = test_dir("finalize");
        let partial = root.join(DOWNLOAD_FILE_NAME);
        let final_path = root.join("codex.exe");
        fs::write(&partial, b"new").unwrap();
        fs::write(&final_path, b"old").unwrap();
        finalize_download(&partial, &final_path).unwrap();
        assert_eq!(fs::read(final_path).unwrap(), b"new");
        assert!(!root.join(BACKUP_FILE_NAME).exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn official_windows_asset_contract_is_pinned() {
        assert!(WINDOWS_X64_ASSET_URL.contains(PINNED_CODEX_VERSION));
        assert_eq!(WINDOWS_X64_SHA256.len(), 64);
        assert_eq!(WINDOWS_X64_ASSET_NAME, "codex-x86_64-pc-windows-msvc.exe");
        assert_eq!(
            WINDOWS_X64_SHA256,
            "51398051c2332b6afe08dc3b9dbb4056085c197f35ca57a307ee303d450cada5"
        );
    }
}
