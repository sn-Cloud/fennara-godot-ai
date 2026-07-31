from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
content = TARGET.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global content
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match, found {count}: {old[:160]!r}")
    content = content.replace(old, new, 1)


replace_once(
    '''    async fn spawn_with_approvals(
        approval_tx: Option<ProviderApprovalSender>,
    ) -> Result<Self, LlmError> {
        let runtime_spec = codex_runtime::resolve_runtime()?;
        let mut command = codex_runtime::build_app_server_command(&runtime_spec)?;
''',
    '''    async fn spawn_with_approvals(
        approval_tx: Option<ProviderApprovalSender>,
    ) -> Result<Self, LlmError> {
        let runtime_spec = codex_runtime::resolve_runtime()?;
        Self::spawn_runtime(runtime_spec, approval_tx).await
    }

    async fn spawn_runtime(
        runtime_spec: codex_runtime::CodexRuntimeSpec,
        approval_tx: Option<ProviderApprovalSender>,
    ) -> Result<Self, LlmError> {
        let mut command = codex_runtime::build_app_server_command(&runtime_spec)?;
''',
)
replace_once(
    '''    async fn process_exit_message(&mut self) -> String {
        let status = self.child.try_wait().ok().flatten();
        let diagnostics = stderr_snapshot(&self.stderr_lines).await;
''',
    '''    async fn process_exit_message(&mut self) -> String {
        let status = self.child.try_wait().ok().flatten();
        if status.is_some() {
            if let Some(task) = self.stderr_task.take() {
                let _ = timeout(Duration::from_millis(500), task).await;
            }
        }
        let diagnostics = stderr_snapshot(&self.stderr_lines).await;
''',
)
replace_once(
    '''#[cfg(test)]
mod tests {
''',
    '''#[cfg(test)]
mod integration_tests;

#[cfg(test)]
mod tests {
''',
)

TARGET.write_text(content, encoding="utf-8", newline="\n")

TESTS = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs"
tests = TESTS.read_text(encoding="utf-8")
old = '''    let error = timeout(
        TEST_TIMEOUT,
        CodexConnection::spawn_runtime(fixture.spec.clone(), None),
    )
    .await
    .expect("crash initialize timed out")
    .expect_err("crash initialize should fail");
'''
new = '''    let result = timeout(
        TEST_TIMEOUT,
        CodexConnection::spawn_runtime(fixture.spec.clone(), None),
    )
    .await
    .expect("crash initialize timed out");
    let error = match result {
        Ok(mut connection) => {
            connection.shutdown().await;
            panic!("crash initialize should fail");
        }
        Err(error) => error,
    };
'''
count = tests.count(old)
if count != 1:
    raise RuntimeError(f"expected one crash result assertion, found {count}")
TESTS.write_text(tests.replace(old, new, 1), encoding="utf-8", newline="\n")

print("phase five migration applied")
