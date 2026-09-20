import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync, rmSync } from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const binaries = ["fennara.exe", "fennara-daemon.exe", "fennara-daemon-runtime.exe", "fennara-mcp.exe", "fennara-mcp-runtime.exe"];
const minimumCodexVersion = [0, 155, 1];

// Validate the vendor's version before replacing a package. Older runtimes can
// silently omit current models even when model/list itself succeeds.
function validateCodexVersion(codexRoot) {
  const metadata = JSON.parse(readFileSync(path.join(codexRoot, "codex-package.json"), "utf8"));
  const version = String(metadata.version || "");
  const parts = /^(\d+)\.(\d+)\.(\d+)$/.exec(version)?.slice(1).map(Number);
  const difference = parts?.map((value, index) => value - minimumCodexVersion[index]).find(value => value !== 0) || 0;
  if (!parts || difference < 0) throw new Error(`Codex ${minimumCodexVersion.join(".")} or newer stable version required; found ${version}`);
}

// Assemble a relocatable addon directory from already-built native components.
// Validate every input first so a missing dependency cannot erase a previous package.
export function packageStandalone({ repo = root, codexRoot, ripgrep }) {
  const version = readFileSync(path.join(repo, "VERSION"), "utf8").trim();
  if (!/^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$/.test(version)) throw new Error("Invalid addon version");
  const source = path.join(repo, "godot_demo/addons/fennara");
  const release = path.join(repo, "local/target/release");
  const dll = "libfennara.windows.editor.x86_64.dll";
  const required = [path.join(source, "bin", dll), ripgrep,
    ...binaries.map(name => path.join(release, name)),
    path.join(codexRoot, "bin/codex.exe"),
    path.join(codexRoot, "codex-resources/codex-command-runner.exe"),
    path.join(codexRoot, "codex-resources/codex-windows-sandbox-setup.exe")];
  for (const file of required) {
    if (!file || !existsSync(file)) throw new Error(`Missing package input: ${file}`);
  }
  validateCodexVersion(codexRoot);
  const output = path.join(repo, "dist", `fennara-addon-windows-x86_64-standalone-v${version}`);
  // The resolved output is always a direct child of this repository's dist directory.
  rmSync(output, { recursive: true, force: true });
  const addon = path.join(output, "addons/fennara");
  cpSync(source, addon, { recursive: true, filter: file => {
    const relative = path.relative(source, file).replaceAll("\\", "/");
    return !["bin", "local", ".godot"].some(dir => relative === dir || relative.startsWith(`${dir}/`));
  }});
  mkdirSync(path.join(addon, "bin"), { recursive: true });
  cpSync(path.join(source, "bin", dll), path.join(addon, "bin", dll));
  cpSync(ripgrep, path.join(addon, "bin/rg-windows-x86_64.exe"));
  const runtime = path.join(addon, "local/windows-x86_64");
  mkdirSync(runtime, { recursive: true });
  for (const name of binaries) cpSync(path.join(release, name), path.join(runtime, name));
  cpSync(codexRoot, path.join(runtime, "codex"), { recursive: true });
  // Godot must not import executables or vendor resources as project assets.
  writeFileSync(path.join(addon, "local/.gdignore"), "\n");
  const files = {};
  const collect = directory => {
    for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) throw new Error(`Bundle symlinks are unsupported: ${file}`);
      if (entry.isDirectory()) collect(file);
      else files[path.relative(runtime, file).replaceAll("\\", "/")] = createHash("sha256").update(readFileSync(file)).digest("hex");
    }
  };
  collect(runtime);
  writeFileSync(path.join(runtime, "bundle.json"), `${JSON.stringify({ version, platform: "windows-x86_64", files }, null, 2)}\n`);
  writeFileSync(path.join(output, "安装说明.txt"), "关闭 Godot，把 addons/fennara 复制到项目的 addons 目录。\n打开项目，在 Fennara 面板点击 Set Up Fennara，然后选择模型或登录 Codex 账号。\n无需安装 Fennara CLI、Node.js 或 Rust。后台从插件包离线准备；聊天记录和运行缓存保存在用户目录。\n更新时关闭 Godot，替换完整 addons/fennara 文件夹。\n");
  return output;
}

// CLI entry point: dependency paths belong to the packager, never the end user.
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const args = process.argv.slice(2);
  if (args.length !== 4 || args[0] !== "--codex-root" || args[2] !== "--ripgrep") {
    throw new Error("Usage: node scripts/package-windows-standalone-addon.mjs --codex-root <native-vendor-directory> --ripgrep <rg.exe>");
  }
  for (const script of ["sync-chat-ui.mjs", "sync-runtime.mjs", "sync-guidance.mjs"]) {
    const result = spawnSync(process.execPath, [path.join(root, "scripts", script)], { cwd: root, stdio: "inherit" });
    if (result.status !== 0) process.exit(result.status ?? 1);
  }
  console.log(packageStandalone({ codexRoot: path.resolve(args[1]), ripgrep: path.resolve(args[3]) }));
}
