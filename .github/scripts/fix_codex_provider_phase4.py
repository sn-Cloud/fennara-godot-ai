from pathlib import Path

path = Path(__file__).resolve().parents[2] / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
content = path.read_text(encoding="utf-8")
old = '''    {
        let mut active = active_login()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if active.is_some() {
            connection.shutdown().await;
            return Err("A Codex ChatGPT login is already in progress.".to_string());
        }
        *active = Some(ActiveCodexLogin {
            login_id: login_id.clone(),
            cancel: cancel_tx,
        });
    }
'''
new = '''    let login_reserved = {
        let mut active = active_login()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if active.is_none() {
            *active = Some(ActiveCodexLogin {
                login_id: login_id.clone(),
                cancel: cancel_tx,
            });
            true
        } else {
            false
        }
    };
    if !login_reserved {
        connection.shutdown().await;
        return Err("A Codex ChatGPT login is already in progress.".to_string());
    }
'''
count = content.count(old)
if count != 1:
    raise RuntimeError(f"expected one active-login reservation block, found {count}")
path.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
