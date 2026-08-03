from pathlib import Path

root = Path(__file__).resolve().parents[2]

integration = root / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs"
text = integration.read_text(encoding="utf-8")
anchor = '''#[tokio::test]
async fn command_approval_accepts_through_provider_control_channel() {
    assert_approval_round_trip(
        "command-approval",
        ProviderApprovalKind::CommandExecution,
        ProviderApprovalDecision::Approved,
    )
    .await;
}
'''
addition = anchor + '''
#[tokio::test]
async fn command_approval_declines_through_provider_control_channel() {
    assert_approval_round_trip(
        "command-approval",
        ProviderApprovalKind::CommandExecution,
        ProviderApprovalDecision::Denied,
    )
    .await;
}
'''
if text.count(anchor) != 1:
    raise SystemExit("command approval anchor mismatch")
text = text.replace(anchor, addition, 1)
anchor = '''#[tokio::test]
async fn file_approval_declines_through_provider_control_channel() {
    assert_approval_round_trip(
        "file-approval",
        ProviderApprovalKind::FileChange,
        ProviderApprovalDecision::Denied,
    )
    .await;
}
'''
addition = anchor + '''
#[tokio::test]
async fn file_approval_accepts_through_provider_control_channel() {
    assert_approval_round_trip(
        "file-approval",
        ProviderApprovalKind::FileChange,
        ProviderApprovalDecision::Approved,
    )
    .await;
}
'''
if text.count(anchor) != 1:
    raise SystemExit("file approval anchor mismatch")
integration.write_text(text.replace(anchor, addition, 1), encoding="utf-8")

providers = root / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs"
text = providers.read_text(encoding="utf-8")
block = '''

    #[test]
    fn codex_registration_preserves_existing_provider_registry_and_routing() {
        let registry = public_provider_registry(&ChatSettings::default());
        let expected = [
            types::ProviderId::CODEX,
            types::ProviderId::OPENAI,
            types::ProviderId::ANTHROPIC,
            types::ProviderId::OPENROUTER,
            types::ProviderId::OLLAMA,
            types::ProviderId::LMSTUDIO,
            types::ProviderId::OLLAMA_CLOUD,
            types::ProviderId::DEEPSEEK,
            types::ProviderId::ZAI,
            types::ProviderId::MOONSHOTAI,
            types::ProviderId::MOONSHOTAI_CN,
            types::ProviderId::KIMI_FOR_CODING,
            types::ProviderId::MINIMAX,
            types::ProviderId::MINIMAX_CODING_PLAN,
            types::ProviderId::MINIMAX_CN,
            types::ProviderId::MINIMAX_CN_CODING_PLAN,
            types::ProviderId::NVIDIA,
        ];
        for provider_id in expected {
            let matches = registry.iter().filter(|provider| provider.id == provider_id).collect::<Vec<_>>();
            assert_eq!(matches.len(), 1, "provider {provider_id} must remain registered exactly once");
            if provider_id == types::ProviderId::CODEX {
                assert_eq!(matches[0].kind, "agent");
                assert_eq!(matches[0].auth.kind, "account");
            } else {
                assert_ne!(matches[0].kind, "agent", "existing provider {provider_id} must not route through Codex");
            }
        }
        assert_eq!(selected_provider_for_model("openai/gpt-5.1"), Some(types::ProviderId::OPENAI));
        assert_eq!(selected_provider_for_model("anthropic/claude-sonnet-4.5"), Some(types::ProviderId::ANTHROPIC));
        assert_eq!(selected_provider_for_model("openrouter/openai/gpt-5.1"), Some(types::ProviderId::OPENROUTER));
        assert_eq!(selected_provider_for_model("ollama/llama3.2"), Some(types::ProviderId::OLLAMA));
        assert_eq!(selected_provider_for_model("lmstudio/local-model"), Some(types::ProviderId::LMSTUDIO));
        assert_eq!(selected_provider_for_model("codex/gpt-5-codex"), Some(types::ProviderId::CODEX));
    }
'''
index = text.rfind("\n}")
if index < 0:
    raise SystemExit("provider tests module closing brace not found")
providers.write_text(text[:index] + block + text[index:], encoding="utf-8")
