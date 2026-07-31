from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI_FILES = [
    ROOT / "ui/chat/app.js",
    ROOT / "godot_demo/addons/fennara/dist/app.js",
]

for path in UI_FILES:
    content = path.read_text(encoding="utf-8")

    replacements = [
        (
            "  const SETTINGS_SAVE_TIMEOUT_MS = 8000;\n",
            "  const SETTINGS_SAVE_TIMEOUT_MS = 8000;\n  const CODEX_RUNTIME_POLL_MS = 500;\n",
            "settings timeout",
        ),
        (
            "  let codexLoginPollTimer = 0;\n  let canRevert = false;\n",
            "  let codexLoginPollTimer = 0;\n  let codexRuntimePollTimer = 0;\n  let codexRuntimeStatus = null;\n  let codexRuntimeInstallRequested = false;\n  let canRevert = false;\n",
            "Codex state",
        ),
        (
            "      requestModelList();\n      requestCodexAccountStatus();\n      flushPendingSettings();\n",
            "      requestModelList();\n      requestCodexRuntimeStatus();\n      requestCodexAccountStatus();\n      flushPendingSettings();\n",
            "daemon open requests",
        ),
        (
            "      stopProjectStatusPolling();\n      mcpAppsSettings?.handleDisconnect();\n",
            "      stopProjectStatusPolling();\n      stopCodexRuntimePolling();\n      mcpAppsSettings?.handleDisconnect();\n",
            "daemon close",
        ),
        (
            '''      if (account.installed === false) {
        return "Codex CLI not installed";
      }
''',
            '''      if (account.installed === false && !codexRuntimeStatus?.installed) {
        if (codexRuntimeStatus?.installing) {
          return `${codexRuntimeProgressLabel(codexRuntimeStatus)} · click to cancel`;
        }
        if (codexRuntimeStatus?.supported) {
          if (codexRuntimeStatus?.repair_required) {
            return "Codex runtime is damaged · click to repair";
          }
          if (codexRuntimeStatus?.error) {
            return "Codex runtime install failed · click to retry";
          }
          return "Install Codex runtime";
        }
        return "Codex CLI not installed";
      }
''',
            "missing Codex status",
        ),
        (
            '''  function requestCodexAccountStatus() {
    return send({
      type: "codex_account_status",
      request_id: nextRequestId("codex-account-status"),
    });
  }

  function stopCodexLoginPolling() {
''',
            '''  function requestCodexRuntimeStatus() {
    return send({
      type: "codex_runtime_status",
      request_id: nextRequestId("codex-runtime-status"),
    });
  }

  function requestCodexAccountStatus() {
    return send({
      type: "codex_account_status",
      request_id: nextRequestId("codex-account-status"),
    });
  }

  function stopCodexRuntimePolling() {
    window.clearInterval(codexRuntimePollTimer);
    codexRuntimePollTimer = 0;
  }

  function startCodexRuntimePolling() {
    stopCodexRuntimePolling();
    codexRuntimePollTimer = window.setInterval(requestCodexRuntimeStatus, CODEX_RUNTIME_POLL_MS);
  }

  function codexRuntimeProgressLabel(status) {
    const downloaded = Number(status?.downloaded_bytes || 0);
    const total = Number(status?.total_bytes || 0);
    const formatBytes = (value) => {
      if (!Number.isFinite(value) || value <= 0) {
        return "0 MB";
      }
      return `${(value / (1024 * 1024)).toFixed(value >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
    };
    if (total > 0) {
      return `Installing Codex runtime ${formatBytes(downloaded)} / ${formatBytes(total)}`;
    }
    return downloaded > 0
      ? `Installing Codex runtime ${formatBytes(downloaded)}`
      : "Starting Codex runtime installation";
  }

  function applyCodexRuntimeStatus(status) {
    codexRuntimeStatus = status || null;
    updateProviderUi();
    if (codexRuntimeStatus?.installing) {
      startCodexRuntimePolling();
      return;
    }
    stopCodexRuntimePolling();
    if (codexRuntimeStatus?.installed) {
      requestCodexAccountStatus();
      if (codexRuntimeInstallRequested) {
        codexRuntimeInstallRequested = false;
        appendSystem("Codex runtime installed. Starting ChatGPT login...");
        send({
          type: "codex_login_start",
          request_id: nextRequestId("codex-login-after-runtime-install"),
        });
      }
      return;
    }
    if (codexRuntimeStatus?.error) {
      codexRuntimeInstallRequested = false;
      appendSystem(codexRuntimeStatus.error);
    }
  }

  function stopCodexLoginPolling() {
''',
            "Codex request helpers",
        ),
        (
            '''    if (!provider.connected) {
      if (provider.account?.signing_in) {
''',
            '''    if (!provider.connected) {
      const runtimeAvailable = provider.account?.installed !== false || codexRuntimeStatus?.installed;
      if (!runtimeAvailable) {
        if (codexRuntimeStatus?.installing) {
          appendSystem("Cancelling Codex runtime installation...");
          codexRuntimeInstallRequested = false;
          send({
            type: "codex_runtime_install_cancel",
            request_id: nextRequestId("codex-runtime-install-cancel"),
          });
          return;
        }
        if (!codexRuntimeStatus?.supported) {
          appendSystem("Codex CLI is not installed, and automatic installation is not supported on this platform yet.");
          return;
        }
        codexRuntimeInstallRequested = true;
        appendSystem(codexRuntimeStatus?.repair_required
          ? "Repairing the Codex runtime..."
          : "Installing the Codex runtime...");
        send({
          type: "codex_runtime_install_start",
          request_id: nextRequestId("codex-runtime-install-start"),
        });
        startCodexRuntimePolling();
        return;
      }
      if (provider.account?.signing_in) {
''',
            "account management",
        ),
        (
            '    if (message.type === "codex_login_started") {\n',
            '    if (message.type === "codex_runtime_status") {\n      applyCodexRuntimeStatus(message.status);\n      return;\n    }\n    if (message.type === "codex_login_started") {\n',
            "runtime message",
        ),
        (
            '      if (requestId.startsWith("open-project-file")) {\n',
            '      if (requestId.startsWith("codex-runtime")) {\n        codexRuntimeInstallRequested = false;\n        stopCodexRuntimePolling();\n        requestCodexRuntimeStatus();\n      }\n      if (requestId.startsWith("open-project-file")) {\n',
            "runtime error",
        ),
    ]

    for old, new, label in replacements:
        count = content.count(old)
        if count != 1:
            raise RuntimeError(f"{path}: expected one {label} block, found {count}")
        content = content.replace(old, new, 1)

    path.write_text(content, encoding="utf-8", newline="\n")

assets = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/assets.rs"
content = assets.read_text(encoding="utf-8")
old = '''        for expected in [
            "codex_login_cancel",
            "compatible_unverified",
            "Click the Codex provider again to cancel",
        ] {
'''
new = '''        for expected in [
            "codex_login_cancel",
            "codex_runtime_install_start",
            "codex_runtime_install_cancel",
            "codex_runtime_status",
            "compatible_unverified",
            "Click the Codex provider again to cancel",
        ] {
'''
count = content.count(old)
if count != 1:
    raise RuntimeError(f"assets.rs: expected one Codex UI marker list, found {count}")
assets.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")

print("phase nine migration applied")
