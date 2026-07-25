from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] if '.github' in str(Path(__file__)) else Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8', newline='\n')


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected exactly one match, found {count}: {old[:100]!r}')
    write(path, content.replace(old, new, 1))


def replace_all_existing(paths: list[str], old: str, new: str) -> None:
    found = 0
    for path in paths:
        target = ROOT / path
        if not target.exists():
            continue
        content = target.read_text(encoding='utf-8')
        count = content.count(old)
        if count:
            target.write_text(content.replace(old, new), encoding='utf-8', newline='\n')
            found += count
    if not found:
        raise RuntimeError(f'no matches found in {paths}: {old[:100]!r}')


# Docs and README reflect the restored scope.
replace_once(
    'README.md',
    '> 当前 `main` 分支已同步上游 Fennara `0.4.0`。现有代码保留完整的 Fennara 架构和功能，当前并未在内置聊天中实现 ChatGPT／Codex 会员账号登录。\n\n本仓库最初计划在完整保留 Fennara 的基础上，增加 OpenAI 官方会员登录能力。该目标仍属于后续扩展方向，不能与当前已经实现的功能混淆。',
    '> 本仓库基于完整的 Fennara `0.4.0`，并恢复 Codex `app-server` 与 ChatGPT 会员账号登录。Fennara 原有 MCP、daemon、CLI、Godot 工具及全部 API Provider 均继续保留。\n\nCodex 会员登录使用本机安装的 OpenAI Codex CLI。OAuth 凭据由 Codex CLI 保存和刷新，本插件不读取或保存 ChatGPT Token。',
)
replace_once(
    'README.md',
    '| ChatGPT／Codex Plus、Pro 等会员账号直接登录内置聊天 | **尚未实现** |',
    '| ChatGPT／Codex Plus、Pro 等会员账号通过 Codex CLI 登录内置聊天 | 已恢复 |',
)
replace_once(
    'README.md',
    'ChatGPT Plus、Pro 等会员订阅与 OpenAI API 是不同的认证和计费体系，会员订阅目前不能直接代替 Fennara 内置聊天所需的 API Key。\n\n外部 Codex 应用通过 MCP 使用 Fennara 时，Codex 的账号登录和模型设置由 Codex 自身负责，不等于 Fennara 内置聊天已经支持会员登录。',
    'OpenAI API Key Provider 与 Codex 会员账号 Provider 相互独立：\n\n- `openai/<model>` 使用 `OPENAI_API_KEY`；\n- `codex/default` 使用 Codex CLI 保存的 ChatGPT 账号；\n- 外部 Codex 应用仍使用自己的账号和模型配置。',
)
replace_once(
    'README.md',
    '> 上述安装命令下载的是上游 Fennara 官方发行版。当前本仓库尚未发布包含自定义会员登录功能的独立发行版。',
    '> 上述安装命令下载的是上游 Fennara 官方发行版，不包含本仓库新增的 Codex 会员登录。使用本功能需要从本仓库构建或等待本仓库独立发行版。',
)
replace_once(
    'docs/providers.md',
    '| OpenAI | Create a key in [OpenAI API keys](https://platform.openai.com/api-keys). Fennara key/env: `OPENAI_API_KEY`. | `openai/<model>` | Uses OpenAI\'s official API. |',
    '| Codex account | Install the official Codex CLI, choose this provider, and complete the ChatGPT browser login. | `codex/default` | Uses `codex app-server`; supports ChatGPT subscription accounts and does not store OAuth tokens in Fennara. |\n| OpenAI | Create a key in [OpenAI API keys](https://platform.openai.com/api-keys). Fennara key/env: `OPENAI_API_KEY`. | `openai/<model>` | Uses OpenAI\'s official API. |',
)
replace_once(
    'docs/providers.md',
    'Cloud providers need your own API key or subscription key. Local providers need\nthe local server running with a model available.',
    'The Codex account provider needs the official Codex CLI and a ChatGPT account login.\nCloud API providers need their own API key or subscription key. Local providers need\nthe local server running with a model available.',
)
replace_once(
    'docs/providers.md',
    '## Custom OpenAI-Compatible Providers\n',
    '## Codex ChatGPT Account\n\n1. Install the official Codex CLI and confirm `codex --version` works.\n2. Open **Chat Settings > Chat > Open providers**.\n3. Choose **Codex (ChatGPT account)**.\n4. Complete the browser OAuth flow.\n5. Select `codex/default`.\n\nFennara starts `codex app-server --stdio` locally. Codex owns the OAuth credentials,\nrefresh tokens, model access, and subscription enforcement. Fennara receives only\naccount status and streamed turn events. The default safety mode is Codex\n`workspaceWrite`; choosing Fennara **Full access** maps the Codex thread to\n`dangerFullAccess`.\n\nConfigure Codex under **Chat Settings > MCP Apps** so the Codex agent can use the\nexisting Fennara MCP tools for Godot-aware editor and runtime operations.\n\n## Custom OpenAI-Compatible Providers\n',
)

print('Codex membership integration applied.')
