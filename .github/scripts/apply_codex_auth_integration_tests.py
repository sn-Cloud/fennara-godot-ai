from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs"
content = TARGET.read_text(encoding="utf-8")
marker = "async fn fixture_login_success_updates_account_state()"
if marker in content:
    print("authentication integration tests already present")
    raise SystemExit(0)

addition = r'''

async fn wait_for_notification(
    connection: &mut CodexConnection,
    expected_method: &str,
) -> Value {
    timeout(TEST_TIMEOUT, async {
        loop {
            let message = connection
                .read_message()
                .await
                .expect("read authentication notification");
            if connection
                .respond_to_server_request(&message)
                .await
                .expect("respond to authentication server request")
            {
                continue;
            }
            if message.get("method").and_then(Value::as_str) == Some(expected_method) {
                return message
                    .get("params")
                    .cloned()
                    .unwrap_or_else(|| json!({}));
            }
        }
    })
    .await
    .unwrap_or_else(|_| panic!("notification timed out: {expected_method}"))
}

async fn read_fixture_account(connection: &mut CodexConnection) -> Value {
    connection
        .request(
            "account/read",
            json!({ "refreshToken": false }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/read failed")
}

#[tokio::test]
async fn fixture_unauthenticated_status_has_no_account() {
    let (_fixture, mut connection) = spawn_fixture("unauthenticated", None).await;
    let account = read_fixture_account(&mut connection).await;
    assert!(account.get("account").is_some_and(Value::is_null));
    assert_eq!(account.get("requiresOpenaiAuth"), Some(&json!(true)));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_login_success_updates_account_state() {
    let (_fixture, mut connection) = spawn_fixture("unauthenticated", None).await;
    let login = connection
        .request(
            "account/login/start",
            json!({
                "type": "chatgpt",
                "useHostedLoginSuccessPage": true,
                "appBrand": "codex"
            }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/login/start failed");
    let login_id = login
        .get("loginId")
        .and_then(Value::as_str)
        .expect("fixture login id")
        .to_string();
    assert_eq!(
        login.get("authUrl").and_then(Value::as_str),
        Some("https://example.invalid/fake-codex-login")
    );

    let completed = wait_for_notification(&mut connection, "account/login/completed").await;
    assert_eq!(completed.get("loginId").and_then(Value::as_str), Some(login_id.as_str()));
    assert_eq!(completed.get("success"), Some(&json!(true)));
    let updated = wait_for_notification(&mut connection, "account/updated").await;
    assert_eq!(updated.get("authMode"), Some(&json!("chatgpt")));
    assert_eq!(updated.get("planType"), Some(&json!("plus")));

    let account = read_fixture_account(&mut connection).await;
    assert_eq!(account.pointer("/account/type"), Some(&json!("chatgpt")));
    assert_eq!(account.pointer("/account/planType"), Some(&json!("plus")));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_login_failure_remains_disconnected_and_retryable() {
    let (_fixture, mut connection) = spawn_fixture("login-failure", None).await;
    connection
        .request(
            "account/login/start",
            json!({ "type": "chatgpt" }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/login/start failed");
    let completed = wait_for_notification(&mut connection, "account/login/completed").await;
    assert_eq!(completed.get("success"), Some(&json!(false)));
    assert!(
        completed
            .get("error")
            .and_then(Value::as_str)
            .is_some_and(|error| error.contains("authentication failed"))
    );
    let account = read_fixture_account(&mut connection).await;
    assert!(account.get("account").is_some_and(Value::is_null));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_login_cancellation_clears_pending_authentication() {
    let (_fixture, mut connection) = spawn_fixture("login-timeout", None).await;
    let login = connection
        .request(
            "account/login/start",
            json!({ "type": "chatgpt" }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/login/start failed");
    let login_id = login
        .get("loginId")
        .and_then(Value::as_str)
        .expect("fixture login id")
        .to_string();
    connection
        .request(
            "account/login/cancel",
            json!({ "loginId": login_id.clone() }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/login/cancel failed");
    let completed = wait_for_notification(&mut connection, "account/login/completed").await;
    assert_eq!(completed.get("loginId").and_then(Value::as_str), Some(login_id.as_str()));
    assert_eq!(completed.get("success"), Some(&json!(false)));
    assert!(
        completed
            .get("error")
            .and_then(Value::as_str)
            .is_some_and(|error| error.contains("cancelled"))
    );
    let account = read_fixture_account(&mut connection).await;
    assert!(account.get("account").is_some_and(Value::is_null));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_logout_removes_connected_account() {
    let (_fixture, mut connection) = spawn_fixture("authenticated", None).await;
    let before = read_fixture_account(&mut connection).await;
    assert_eq!(before.pointer("/account/type"), Some(&json!("chatgpt")));
    connection
        .request("account/logout", json!({}), TEST_TIMEOUT)
        .await
        .expect("account/logout failed");
    let updated = wait_for_notification(&mut connection, "account/updated").await;
    assert!(updated.get("authMode").is_some_and(Value::is_null));
    let after = read_fixture_account(&mut connection).await;
    assert!(after.get("account").is_some_and(Value::is_null));
    connection.shutdown().await;
}

#[tokio::test]
async fn public_account_status_surface_never_serializes_credentials() {
    let account = json!({
        "account": {
            "type": "chatgpt",
            "email": "fixture@example.invalid",
            "planType": "plus",
            "accessToken": "must-not-escape",
            "refreshToken": "must-not-escape",
            "cookie": "must-not-escape"
        },
        "requiresOpenaiAuth": true
    });
    let status = account_status_from_result(&account, true, false, None);
    let serialized = serde_json::to_string(&status).expect("serialize public account status");
    assert!(serialized.contains("fixture@example.invalid"));
    for forbidden in ["accessToken", "refreshToken", "cookie", "must-not-escape"] {
        assert!(!serialized.contains(forbidden), "credential leaked through status: {forbidden}");
    }
}
'''

TARGET.write_text(content.rstrip() + addition + "\n", encoding="utf-8", newline="\n")
print("Codex authentication integration tests added")
