from pathlib import Path


path = Path(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
)
text = path.read_text(encoding="utf-8")
old = '''    async fn process_exit_message(&mut self) -> String {
        let status = self.child.try_wait().ok().flatten();
        if status.is_some() {
            if let Some(task) = self.stderr_task.take() {
                let _ = timeout(Duration::from_millis(500), task).await;
            }
        }
'''
new = '''    async fn process_exit_message(&mut self) -> String {
        let status = match self.child.try_wait() {
            Ok(Some(status)) => Some(status),
            Ok(None) => match timeout(Duration::from_millis(500), self.child.wait()).await {
                Ok(Ok(status)) => Some(status),
                _ => None,
            },
            Err(_) => None,
        };
        if status.is_some() {
            if let Some(task) = self.stderr_task.take() {
                let _ = timeout(Duration::from_millis(500), task).await;
            }
        }
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one process_exit_message match, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
