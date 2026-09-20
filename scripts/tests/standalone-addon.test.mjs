import test from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { packageStandalone } from "../package-windows-standalone-addon.mjs";

test("complete addon preserves Codex helpers and verifies every runtime file after relocation", () => {
  const temp = path.resolve("temp/standalone-tests");
  mkdirSync(temp, { recursive: true });
  const repo = mkdtempSync(path.join(temp, "package-"));
  const put = (name, content = name) => {
    const target = path.join(repo, name);
    mkdirSync(path.dirname(target), { recursive: true });
    writeFileSync(target, content);
    return target;
  };
  try {
    put("VERSION", "0.4.3\n");
    put("godot_demo/addons/fennara/VERSION", "0.4.3\n");
    put("godot_demo/addons/fennara/fennara.gdextension");
    put("godot_demo/addons/fennara/bin/libfennara.windows.editor.x86_64.dll");
    put("godot_demo/addons/fennara/bin/unwanted-linux.so");
    put("godot_demo/addons/fennara/local/stale.exe");
    for (const name of ["fennara", "fennara-daemon", "fennara-daemon-runtime", "fennara-mcp", "fennara-mcp-runtime"]) put(`local/target/release/${name}.exe`);
    put("vendor/bin/codex.exe");
    put("vendor/codex-resources/codex-command-runner.exe");
    put("vendor/codex-resources/codex-windows-sandbox-setup.exe");
    put("vendor/codex-package.json", '{"version":"0.155.1"}');
    const options = { repo, codexRoot: path.join(repo, "vendor"), ripgrep: put("rg.exe") };
    const output = packageStandalone(options);
    const addon = path.join(output, "addons/fennara");
    assert.ok(existsSync(path.join(addon, "local/.gdignore")));
    assert.ok(!existsSync(path.join(addon, "local/stale.exe")));
    assert.ok(!existsSync(path.join(addon, "bin/unwanted-linux.so")));
    const runtime = path.join(addon, "local/windows-x86_64");
    const manifest = JSON.parse(readFileSync(path.join(runtime, "bundle.json")));
    assert.ok(manifest.files["codex/codex-resources/codex-command-runner.exe"]);
    for (const [name, hash] of Object.entries(manifest.files)) assert.equal(createHash("sha256").update(readFileSync(path.join(runtime, name))).digest("hex"), hash);
    const previous = readFileSync(path.join(runtime, "bundle.json"), "utf8");
    for (const version of ["0.145.0", "0.155.0", "0.155.1-alpha.1", "invalid"]) {
      put("vendor/codex-package.json", JSON.stringify({ version }));
      assert.throws(() => packageStandalone(options), /newer stable version required/);
      assert.equal(readFileSync(path.join(runtime, "bundle.json"), "utf8"), previous);
    }
    put("vendor/codex-package.json", '{"version":"0.155.1"}');
    rmSync(path.join(repo, "vendor/bin/codex.exe"));
    assert.throws(() => packageStandalone(options), /Missing package input/);
    assert.equal(readFileSync(path.join(runtime, "bundle.json"), "utf8"), previous);
  } finally {
    rmSync(repo, { recursive: true, force: true });
  }
});
