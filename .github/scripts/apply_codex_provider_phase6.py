from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
UI_FILES = [
    ROOT / "ui/chat/app.js",
    ROOT / "godot_demo/addons/fennara/dist/app.js",
]

status_pattern = re.compile(
    r'''      if \(account\.signing_in\) \{\n        return "Waiting for browser login";\n      \}\n      if \(provider\.connected\) \{\n        const plan = String\(account\.plan_type \|\| ""\)\.trim\(\);\n        return plan \? `Connected · \$\{plan\}` : "Connected";\n      \}'''
)
status_replacement = '''      if (account.signing_in) {
        return "Waiting for browser login · click to cancel";
      }
      if (provider.connected) {
        const plan = String(account.plan_type || "").trim();
        const runtime = account.runtime || {};
        const version = String(runtime.version || "").trim();
        const platform = String(runtime.platform || "").trim();
        const compatibility = String(runtime.compatibility || "").trim();
        const details = [];
        if (plan) {
          details.push(plan);
        }
        if (version) {
          details.push(`Codex ${version}`);
        }
        if (platform && platform !== "unsupported") {
          details.push(platform);
        }
        if (compatibility === "tested") {
          details.push("tested runtime");
        } else if (compatibility === "compatible_unverified") {
          details.push("unverified runtime");
        } else if (compatibility === "unknown") {
          details.push("unknown runtime");
        }
        return details.length ? `Connected · ${details.join(" · ")}` : "Connected";
      }'''

manage_pattern = re.compile(
    r'''    if \(!provider\.connected\) \{\n      appendSystem\("Starting Codex ChatGPT login\.\.\."\);\n      send\(\{\n        type: "codex_login_start",\n        request_id: nextRequestId\("codex-login-start"\),\n      \}\);\n      return;\n    \}'''
)
manage_replacement = '''    if (!provider.connected) {
      if (provider.account?.signing_in) {
        appendSystem("Cancelling Codex ChatGPT login...");
        send({
          type: "codex_login_cancel",
          request_id: nextRequestId("codex-login-cancel"),
        });
        return;
      }
      appendSystem("Starting Codex ChatGPT login...");
      send({
        type: "codex_login_start",
        request_id: nextRequestId("codex-login-start"),
      });
      return;
    }'''

login_message_old = '        appendSystem(`Complete Codex login in your browser: ${authUrl}`);\n'
login_message_new = '        appendSystem(`Complete Codex login in your browser: ${authUrl}. Click the Codex provider again to cancel.`);\n'

for path in UI_FILES:
    content = path.read_text(encoding="utf-8")
    content, count = status_pattern.subn(status_replacement, content)
    if count != 1:
        raise RuntimeError(f"{path}: expected one Codex account status block, found {count}")
    content, count = manage_pattern.subn(manage_replacement, content)
    if count != 1:
        raise RuntimeError(f"{path}: expected one Codex account management block, found {count}")
    count = content.count(login_message_old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one Codex login browser message, found {count}")
    content = content.replace(login_message_old, login_message_new, 1)
    path.write_text(content, encoding="utf-8", newline="\n")

assets = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/assets.rs"
content = assets.read_text(encoding="utf-8")
marker = '''    #[test]
    fn browser_chat_stylesheet_imports_are_embedded() {
'''
insert = '''    #[test]
    fn codex_account_ui_exposes_cancel_and_runtime_compatibility() {
        let source = include_str!("../../../../../../ui/chat/app.js");
        let distributed =
            include_str!("../../../../../../godot_demo/addons/fennara/dist/app.js");
        assert_eq!(source, distributed, "source and distributed chat UI must match");
        for expected in [
            "codex_login_cancel",
            "compatible_unverified",
            "Click the Codex provider again to cancel",
        ] {
            assert!(distributed.contains(expected), "missing Codex UI marker: {expected}");
        }
    }

    #[test]
    fn browser_chat_stylesheet_imports_are_embedded() {
'''
count = content.count(marker)
if count != 1:
    raise RuntimeError(f"assets.rs: expected one stylesheet test marker, found {count}")
assets.write_text(content.replace(marker, insert, 1), encoding="utf-8", newline="\n")

runtime = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs"
content = runtime.read_text(encoding="utf-8")
for block in [
    '''impl CodexRuntimeSource {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Configured => "configured",
            Self::Path => "path",
        }
    }
}

''',
    '''impl CodexCompatibility {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Tested => "tested",
            Self::CompatibleUnverified => "compatible_unverified",
            Self::Unknown => "unknown",
        }
    }
}

''',
]:
    count = content.count(block)
    if count != 1:
        raise RuntimeError(f"codex_runtime.rs: expected one unused helper block, found {count}")
    content = content.replace(block, "", 1)
runtime.write_text(content, encoding="utf-8", newline="\n")

print("phase six migration applied")
