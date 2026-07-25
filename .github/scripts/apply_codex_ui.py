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


# Provider popover account flow.
for path in ['ui/chat/provider-popovers.js', 'godot_demo/addons/fennara/dist/provider-popovers.js']:
    replace_once(
        path,
        '    const chooseProvider = callbacks.chooseProvider || noop;\n',
        '    const chooseProvider = callbacks.chooseProvider || noop;\n    const manageAccountProvider = callbacks.manageAccountProvider || noop;\n',
    )
    replace_once(
        path,
        '        if (isCustom) {\n          openCustomProviderPrompt(provider);\n          return;\n        }\n        if (canUpdateKey) {',
        '        if (isCustom) {\n          openCustomProviderPrompt(provider);\n          return;\n        }\n        if (provider.auth?.type === "account") {\n          manageAccountProvider(provider);\n          return;\n        }\n        if (canUpdateKey) {',
    )

# Composer blocks account providers until signed in.
for path in ['ui/chat/composer-actions.js', 'godot_demo/addons/fennara/dist/composer-actions.js']:
    replace_once(
        path,
        '    const providerRequiresApiKey = callbacks.providerRequiresApiKey || (() => false);\n    const providerConnected = callbacks.providerConnected || (() => false);',
        '    const providerRequiresApiKey = callbacks.providerRequiresApiKey || (() => false);\n    const providerRequiresAccount = callbacks.providerRequiresAccount || (() => false);\n    const providerConnected = callbacks.providerConnected || (() => false);',
    )
    replace_once(
        path,
        '      if (providerRequiresApiKey(currentProvider) && !providerConnected(currentProvider)) {\n        openProviderPicker();\n        return;\n      }',
        '      if ((providerRequiresApiKey(currentProvider) || providerRequiresAccount(currentProvider))\n          && !providerConnected(currentProvider)) {\n        openProviderPicker();\n        return;\n      }',
    )

# Main UI login lifecycle.
for path in ['ui/chat/app.js', 'godot_demo/addons/fennara/dist/app.js']:
    replace_once(
        path,
        '  let projectStatusTimer = 0;\n',
        '  let projectStatusTimer = 0;\n  let codexLoginPollTimer = 0;\n',
    )
    replace_once(
        path,
        '      requestModelList();\n      flushPendingSettings();\n',
        '      requestModelList();\n      requestCodexAccountStatus();\n      flushPendingSettings();\n',
    )
    replace_once(
        path,
        '      providerUsesBaseUrlSetup,\n      chooseProvider,\n',
        '      providerUsesBaseUrlSetup,\n      chooseProvider,\n      manageAccountProvider,\n',
    )
    replace_once(
        path,
        '      providerRequiresApiKey,\n      providerConnected,\n',
        '      providerRequiresApiKey,\n      providerRequiresAccount,\n      providerConnected,\n',
    )
    replace_once(
        path,
        '      custom: provider?.custom || null,\n',
        '      custom: provider?.custom || null,\n      account: provider?.account || null,\n',
    )
    replace_once(
        path,
        '    if (provider.auth?.type === "api_key") {\n      return provider.connected ? "Connected" : "Not connected";\n    }\n',
        '    if (provider.auth?.type === "api_key") {\n      return provider.connected ? "Connected" : "Not connected";\n    }\n    if (provider.auth?.type === "account") {\n      const account = provider.account || {};\n      if (account.installed === false) {\n        return "Codex CLI not installed";\n      }\n      if (account.signing_in) {\n        return "Waiting for browser login";\n      }\n      if (provider.connected) {\n        const plan = String(account.plan_type || "").trim();\n        return plan ? `Connected · ${plan}` : "Connected";\n      }\n      return "Sign in with ChatGPT";\n    }\n',
    )
    replace_once(
        path,
        '  function providerRequiresApiKey(providerId) {\n    return providerMetadata.get(providerId)?.auth?.type === "api_key";\n  }\n',
        '  function providerRequiresApiKey(providerId) {\n    return providerMetadata.get(providerId)?.auth?.type === "api_key";\n  }\n\n  function providerRequiresAccount(providerId) {\n    return providerMetadata.get(providerId)?.auth?.type === "account";\n  }\n',
    )
    replace_once(
        path,
        '    if (providerRequiresApiKey(currentProvider)) {\n      return providerConnected(currentProvider);\n    }\n',
        '    if (providerRequiresApiKey(currentProvider) || providerRequiresAccount(currentProvider)) {\n      return providerConnected(currentProvider);\n    }\n',
    )
    replace_once(
        path,
        '  function chooseProvider(provider) {\n',
        '  function requestCodexAccountStatus() {\n    return send({\n      type: "codex_account_status",\n      request_id: nextRequestId("codex-account-status"),\n    });\n  }\n\n  function stopCodexLoginPolling() {\n    window.clearInterval(codexLoginPollTimer);\n    codexLoginPollTimer = 0;\n  }\n\n  function startCodexLoginPolling() {\n    stopCodexLoginPolling();\n    codexLoginPollTimer = window.setInterval(requestCodexAccountStatus, 1500);\n  }\n\n  function applyCodexAccountStatus(status) {\n    const next = status || {};\n    let changed = false;\n    providerRegistry = providerRegistry.map((provider) => {\n      if (provider.id !== "codex") {\n        return provider;\n      }\n      changed = provider.connected !== Boolean(next.connected) || provider.account !== next;\n      return { ...provider, connected: Boolean(next.connected), account: next };\n    });\n    if (changed) {\n      providerMetadata = new Map(providerRegistry.map((provider) => [provider.id, provider]));\n      updateProviderUi();\n      updateModelUi();\n      modelPicker?.applyCatalog({\n        ...(lastModelCatalog || {}),\n        providers: providerRegistry,\n      });\n    }\n    if (next.connected) {\n      stopCodexLoginPolling();\n    } else if (next.error && !next.signing_in) {\n      stopCodexLoginPolling();\n    }\n  }\n\n  function manageAccountProvider(provider) {\n    if (provider.id !== "codex") {\n      chooseProvider(provider.id);\n      return;\n    }\n    if (!provider.connected) {\n      appendSystem("Starting Codex ChatGPT login...");\n      send({\n        type: "codex_login_start",\n        request_id: nextRequestId("codex-login-start"),\n      });\n      return;\n    }\n    if (currentProvider === provider.id) {\n      if (window.confirm("Sign out of the Codex ChatGPT account?")) {\n        send({\n          type: "codex_logout",\n          request_id: nextRequestId("codex-logout"),\n        });\n      }\n      return;\n    }\n    chooseProvider(provider.id);\n  }\n\n  function chooseProvider(provider) {\n',
    )
    replace_once(
        path,
        '    if (message.type === "chat_reset") {\n',
        '    if (message.type === "codex_login_started") {\n      const authUrl = String(message.login?.auth_url || "");\n      if (authUrl) {\n        window.open(authUrl, "_blank", "noopener,noreferrer");\n        appendSystem(`Complete Codex login in your browser: ${authUrl}`);\n      } else {\n        appendSystem("Codex did not return a browser login URL.");\n      }\n      startCodexLoginPolling();\n      requestCodexAccountStatus();\n      return;\n    }\n    if (message.type === "codex_account_status") {\n      const wasConnected = providerConnected("codex");\n      applyCodexAccountStatus(message.status);\n      if (message.status?.connected && !wasConnected) {\n        currentProvider = "codex";\n        if (!currentModel || providerFromModel(currentModel) !== "codex") {\n          currentModel = "codex/default";\n        }\n        updateProviderUi();\n        updateModelUi();\n        saveCurrentChatSettings();\n        requestModelList({ refreshLocal: false });\n        appendSystem("Codex ChatGPT account connected.");\n        window.setTimeout(clearSystemStatus, 2200);\n      } else if (message.status?.error && !message.status?.signing_in) {\n        appendSystem(message.status.error);\n      }\n      return;\n    }\n    if (message.type === "chat_reset") {\n',
    )
