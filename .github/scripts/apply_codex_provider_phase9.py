from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
UI_FILES = [
    ROOT / "ui/chat/app.js",
    ROOT / "godot_demo/addons/fennara/dist/app.js",
]

for path in UI_FILES:
    content = path.read_text(encoding="utf-8")

    old = '''  const SETTINGS_SAVE_TIMEOUT_MS = 8000;
'''
    new = '''  const SETTINGS_SAVE_TIMEOUT_MS = 8000;
  const CODEX_RUNTIME_POLL_MS = 500;
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected settings timeout marker")
    content = content.replace(old, new, 1)

    old = '''  let codexLoginPollTimer = 0;
  let canRevert = false;
'''
    new = '''  let codexLoginPollTimer = 0;
  let codexRuntimePollTimer = 0;
  let codexRuntimeStatus = null;
  let codexRuntimeInstallRequested = false;
  let canRevert = false;
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected Codex state marker")
    content = content.replace(old, new, 1)

    old = '''      requestModelList();
      requestCodexAccountStatus();
      flushPendingSettings();
'''
    new = '''      requestModelList();
      requestCodexRuntimeStatus();
      requestCodexAccountStatus();
      flushPendingSettings();
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected daemon open requests")
    content = content.replace(old, new, 1)

    old = '''      stopProjectStatusPolling();
      mcpAppsSettings?.handleDisconnect();
'''
    new = '''      stopProjectStatusPolling();
      stopCodexRuntimePolling();
      mcpAppsSettings?.handleDisconnect();
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected daemon close marker")
    content = content.replace(old, new, 1)

    old = '''      if (account.installed === false) {
        return "Codex CLI not installed";
      }
'''
    new = '''      if (account.installed === false && !codexRuntimeStatus?.installed) {
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
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected missing Codex status block")
    content = content.replace(old, new, 1)

    old = '''  function requestCodexAccountStatus() {
    return send({
      type: "codex_account_status",
      request_id: nextRequestId("codex-account-status"),
    });
  }

  function stopCodexLoginPolling() {
'''
    new = '''  function requestCodexRuntimeStatus() {
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
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected Codex account request block")
    content = content.replace(old, new, 1)

    old = '''    if (!provider.connected) {
      if (provider.account?.signing_in) {
'''
    new = '''    if (!provider.connected) {
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
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected account provider management block")
    content = content.replace(old, new, 1)

    old = '''    if (message.type === "codex_login_started") {
'''
    new = '''    if (message.type === "codex_runtime_status") {
      applyCodexRuntimeStatus(message.status);
      return;
    }
    if (message.type === "codex_login_started") {
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected Codex login message marker")
    content = content.replace(old, new, 1)

    old = '''      if (requestId.startsWith("open-project-file")) {
'''
    new = '''      if (requestId.startsWith("codex-runtime")) {
        codexRuntimeInstallRequested = false;
        stopCodexRuntimePolling();
        requestCodexRuntimeStatus();
      }
      if (requestId.startsWith("open-project-file")) {
'''
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: expected error request marker")
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
if content.count(old) != 1:
    raise RuntimeError("assets.rs: expected Codex UI marker list")
assets.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")

print("phase nine migration applied")
