# Agent Instructions

Read this file before changing the repository.

## Core Rules

- Keep changes small, focused, and easy to review.
- Prefer simple code and clear ownership boundaries.
- Do not add game-specific MCP tools or guidance. Fennara should expose Godot feedback and primitive controls, not assumptions about a particular game's movement, combat, inventory, quests, UI flow, or objectives.
- Do not publish releases, create tags, or run release workflows unless a maintainer explicitly asks for that exact action.
- Keep branch names human-readable and do not prefix Codex-created branches with `codex/`.
- Do not change GitHub Actions release behavior casually. Explain any workflow change in the pull request.
- Keep platform-specific native code behind explicit platform files or small bridge boundaries. Windows, macOS, Linux, and unsupported fallback behavior should remain obvious from filenames and call sites.
- Do not bundle heavyweight browser runtimes into the Godot addon. Linux CEF is a shared local webview runtime installed under the user's Fennara app-data directory, not copied into every `res://addons/fennara/`.

## Repository Layout

Fennara is a game-agnostic Godot AI addon: an in-editor chat webview, an external MCP server, and a shared local daemon, installed and updated by a CLI.

- `local/` is the Rust workspace: `fennara-cli`, `fennara-daemon`, `fennara-project-identity`, `fennara-mcp`, plus shared tool schemas in `local/schemas/tools/` and install templates in `local/templates/`.
- `fennara-cpp/` is the C++ GDExtension (SCons build, `godot-cpp/` submodule) for Godot editor integration, tools, and the webview host.
- `ui/chat/` is the buildless web chat UI source (plain HTML/CSS/JS, no package.json; vendored libraries under `ui/chat/vendor/`).
- `runtime/` holds the GDScript runtime helpers used by `runtime_session` and `runtime_script`.
- `godot_demo/addons/fennara/` is the installable addon payload; `godot_demo/tests/` holds headless Godot regression tests.
- `scripts/` holds Node automation for versioning, packaging, release validation, and doc i18n.

Use `docs/repo-map.md` as the detailed "where to change things" index before starting.

## Source Of Truth

- `README.md` is the human-facing project overview.
- `llms.txt` is the short index for language models and coding agents.
- `CONTEXT.md` defines shared Fennara vocabulary.
- `docs/repo-map.md` explains repository layout.
- `docs/architecture.md` explains the high-level system.
- `docs/release.md` explains release expectations.
- `local/templates/` contains project guidance written by `fennara install` and refreshed by `fennara update`.
- `ui/chat/` contains the source web chat UI. `godot_demo/addons/fennara/dist/` is the synced addon copy.
- `runtime/` contains the source Godot runtime helper scripts. `godot_demo/addons/fennara/runtime/` is the synced addon copy.

## Build And Test Commands

- Rust workspace, run from `local/`: `cargo test --locked` and `cargo build --release --locked`.
- Node tests: `node --test scripts/tests/<name>.test.mjs` from the repo root; each `*.test.mjs` is standalone.
- Version sync: `node scripts/check-version.mjs`.
- Docs i18n validation: `node scripts/sync-doc-navigation.mjs --check` then `node scripts/check-doc-i18n.mjs`.
- GDExtension, run from `fennara-cpp/`: `scons platform=windows target=editor` (same for `macos`/`linux`; Linux CI first prepares the pinned CEF SDK via `node scripts/prepare-linux-cef-sdk.mjs` — see `.github/workflows/gdextension-build.yml`).

## Generated And Packaged Files

- After editing `ui/chat/`, run `node scripts/sync-chat-ui.mjs` and commit the matching `godot_demo/addons/fennara/dist/` changes.
- After editing `runtime/`, run `node scripts/sync-runtime.mjs` and commit the matching `godot_demo/addons/fennara/runtime/` changes.
- After editing `local/templates/fennara-guidelines.md`, run `node scripts/sync-guidance.mjs` and commit the matching `godot_demo/addons/fennara/ai/guidelines.md` changes.
- Do not hand-edit generated addon webview files in `godot_demo/addons/fennara/dist/` without also updating the source in `ui/chat/`.
- Do not hand-edit synced addon runtime helpers in `godot_demo/addons/fennara/runtime/` without also updating the source in `runtime/`.
- Do not hand-edit generated addon guidance in `godot_demo/addons/fennara/ai/guidelines.md` without also updating `local/templates/fennara-guidelines.md`.
- Root `dist/` and `.package-preview/` are build outputs and should stay untracked.
- `godot_demo/addons/fennara/dist/` is intentionally tracked because release addon zips must contain the built chat UI.
- `godot_demo/addons/fennara/runtime/` is intentionally tracked because release addon zips must contain the Godot runtime helper scripts.
- `godot_demo/addons/fennara/ai/guidelines.md` is intentionally tracked because release addon zips should mirror the installed addon guidance layout.

## Documentation Updates

When changing tool behavior, setup behavior, or release behavior, update the relevant docs in the same pull request.

When adding source areas, update `docs/repo-map.md` so contributors and agents can find the right files quickly.

When changing Linux webview runtime installation, update the release docs and keep package-preview limitations explicit. Package Preview is for test artifacts; Release is the source of truth for user-facing install assets.

## Pull Requests

- Use Conventional Commit style for pull request titles.
- Keep descriptions short and specific.
- Explain how the change was verified.
- Avoid unrelated cleanup in feature or fix pull requests.
