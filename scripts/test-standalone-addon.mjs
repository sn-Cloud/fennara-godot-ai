import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync, renameSync } from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import net from "node:net";
import { fileURLToPath } from "node:url";

// Exercise the native setup flow used by the button, installer process, and daemon
// using a relocated addon and a fresh user-data directory. Never stop a user's daemon.
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const [godot, packageDir] = process.argv.slice(2);
if (!godot || !packageDir) throw new Error("Usage: node scripts/test-standalone-addon.mjs <godot.exe> <complete-addon-directory>");
await new Promise((resolve, reject) => {
  const socket = net.connect(41287, "127.0.0.1");
  socket.once("connect", () => { socket.destroy(); reject(new Error("Close the existing Fennara daemon before this isolated test")); });
  socket.once("error", error => error.code === "ECONNREFUSED" ? resolve() : reject(error));
});
mkdirSync(path.join(repo, "temp"), { recursive: true });
const fixture = mkdtempSync(path.join(repo, "temp/standalone-smoke-"));
const project = path.join(fixture, "relocated project");
const userData = path.join(fixture, "user-data");
cpSync(path.join(path.resolve(packageDir), "addons"), path.join(project, "addons"), { recursive: true });
mkdirSync(path.join(project, ".godot"), { recursive: true });
mkdirSync(path.join(userData, "Fennara"), { recursive: true });
writeFileSync(path.join(project, "project.godot"), '[application]\nconfig/name="Standalone setup smoke"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n');
writeFileSync(path.join(project, ".godot/extension_list.cfg"), "res://addons/fennara/fennara.gdextension\n");
writeFileSync(path.join(project, ".godot/.gdignore"), "");
writeFileSync(path.join(userData, "Fennara/chat_settings.json"), '{"telemetry_enabled":false}');
// Simulate an official installation with the same version but without our bundle id.
const version = readFileSync(path.join(project, "addons/fennara/VERSION"), "utf8").trim();
writeFileSync(path.join(userData, "Fennara/current.json"), JSON.stringify({ version }));
mkdirSync(path.join(userData, "Fennara/bin"), { recursive: true });
for (const name of ["fennara.exe", "fennara-daemon.exe"]) writeFileSync(path.join(userData, "Fennara/bin", name), "old-build-placeholder");
writeFileSync(path.join(project, "smoke.gd"), `extends SceneTree
var setup: Node
var elapsed := 0.0
func _initialize():
    call_deferred("begin")
func begin():
    setup = ClassDB.instantiate("FirstRunSetup")
    root.add_child(setup)
    if not setup.is_setup_required():
        push_error("An unverified same-version runtime bypassed setup")
        quit(1)
        return
    # Call the same native setup method used by the panel's button.
    setup.start(ProjectSettings.globalize_path("res://"), FileAccess.get_file_as_string("res://addons/fennara/VERSION").strip_edges())
func _process(delta):
    elapsed += delta
    if setup == null:
        return false
    if setup.has_failed():
        if OS.get_environment("EXPECT_BUNDLE_FAILURE") == "1":
            print("FENNARA_BUNDLED_FAILURE_OK")
            quit(0)
            return false
        push_error(setup.get_error_code() + ": " + setup.get_detail())
        quit(1)
    elif setup.has_succeeded():
        if OS.get_environment("EXPECT_BUNDLE_FAILURE") == "1":
            push_error("An incomplete bundle was accepted")
            quit(1)
            return false
        if setup.is_setup_required():
            push_error("Setup succeeded without matching runtime")
            quit(1)
        else:
            print("FENNARA_BUNDLED_SETUP_OK")
            quit(0)
    elif elapsed > 45:
        push_error("Setup timed out: " + setup.get_status())
        quit(1)
    return false
`);
mkdirSync(path.join(fixture, "profile"), { recursive: true });
const env = { ...process.env, LOCALAPPDATA: userData, APPDATA: userData, USERPROFILE: path.join(fixture, "profile"), FENNARA_DISABLE_NATIVE_WEBVIEW: "1" };
let result;
try {
  result = spawnSync(godot, ["--headless", "--path", project, "--script", "res://smoke.gd"], { env, encoding: "utf8", timeout: 60000, windowsHide: true });
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}\n${result.error ?? ""}`);
  assert.match(result.stdout, /FENNARA_BUNDLED_SETUP_OK/);
  const current = JSON.parse(readFileSync(path.join(userData, "Fennara/current.json")));
  const manifest = readFileSync(path.join(project, "addons/fennara/local/windows-x86_64/bundle.json"));
  assert.equal(current.bundle_id, createHash("sha256").update(manifest).digest("hex"));
  assert.ok(current.daemon_runtime.startsWith(path.join(userData, "Fennara/versions")));
  const health = await (await fetch("http://127.0.0.1:41287/health", { signal: AbortSignal.timeout(5000) })).json();
  assert.equal(health.version, version);
  const codex = spawnSync(path.join(path.dirname(current.daemon_runtime), "codex/bin/codex.exe"), ["--version"], { env, encoding: "utf8", windowsHide: true });
  assert.equal(codex.status, 0, codex.stderr);
  // A real editor must connect to the prepared runtime without another install.
  const headers = { "X-Fennara-Control-Token": readFileSync(path.join(userData, "Fennara/daemon-control-token"), "utf8").trim() };
  const editor = spawn(godot, ["--headless", "--editor", "--path", project, "--max-fps", "30", "--quit-after", "240"], { env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  let editorLog = "";
  editor.stdout.on("data", data => { editorLog += data; });
  editor.stderr.on("data", data => { editorLog += data; });
  const editorExit = new Promise((resolve, reject) => { editor.on("exit", resolve); editor.on("error", reject); });
  let connected = false;
  try {
    for (let attempt = 0; attempt < 35 && editor.exitCode === null; attempt++) {
      const status = await (await fetch("http://127.0.0.1:41287/status", { headers, signal: AbortSignal.timeout(3000) })).json();
      if (status.godot_plugin_connected && status.connected_projects.some(item => item.plugin_version === version)) { connected = true; break; }
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    assert.ok(connected, `Editor did not connect:\n${editorLog}`);
  } finally {
    const timer = setTimeout(() => editor.kill(), 15000);
    await editorExit;
    clearTimeout(timer);
  }
  // Missing manifests must fail locally, never fall back to an online release.
  const bundlePath = path.join(project, "addons/fennara/local/windows-x86_64/bundle.json");
  renameSync(bundlePath, `${bundlePath}.saved`);
  try {
    const failure = spawnSync(godot, ["--headless", "--path", project, "--script", "res://smoke.gd"], { env: { ...env, EXPECT_BUNDLE_FAILURE: "1" }, encoding: "utf8", timeout: 60000, windowsHide: true });
    assert.equal(failure.status, 0, `${failure.stdout}\n${failure.stderr}`);
    assert.match(failure.stdout, /FENNARA_BUNDLED_FAILURE_OK/);
  } finally { renameSync(`${bundlePath}.saved`, bundlePath); }
  console.log(`PASS: relocated addon, isolated setup, exact bundle identity, daemon ${health.version}, ${codex.stdout.trim()}`);
  console.log("PASS: real editor connection and incomplete-bundle failure");
  console.log(`Evidence: ${fixture}`);
} finally {
  const tokenPath = path.join(userData, "Fennara/daemon-control-token");
  if (existsSync(tokenPath)) {
    await fetch("http://127.0.0.1:41287/shutdown", { method: "POST", signal: AbortSignal.timeout(5000), headers: { "X-Fennara-Control-Token": readFileSync(tokenPath, "utf8").trim() } }).catch(() => {});
  }
}
