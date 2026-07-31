from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs');s=p.read_text();m='    fn custom_provider_config() -> custom::CustomProviderConfig {\n';b='''    #[test]
    fn external_mcp_activity_does_not_create_fennara_tool_call() {
        let mut accumulator = StreamAccumulator::default();
        let items = accumulator
            .items_for_event(StreamEvent::ExternalToolActivity {
                id: "mcp-1".to_string(),
                name: "fennara · get_scene_tree".to_string(),
                arguments: "{}".to_string(),
                content: "scene tree".to_string(),
                status: "completed".to_string(),
            })
            .unwrap();
        assert_eq!(accumulator.observed_tool_calls, 0);
        assert_eq!(items.len(), 1);
        assert!(matches!(items[0], StreamItem::ExternalTool { .. }));
    }

'''
if 'external_mcp_activity_does_not_create_fennara_tool_call' not in s:
    if s.count(m)!=1: raise RuntimeError('provider tests marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
