use serde_json::Value;
use tokio::sync::{mpsc, oneshot};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ProviderApprovalKind {
    CommandExecution,
    FileChange,
}

impl ProviderApprovalKind {
    pub(crate) fn tool_name(self) -> &'static str {
        match self {
            Self::CommandExecution => "codex_command_execution",
            Self::FileChange => "codex_file_change",
        }
    }

    pub(crate) fn label(self) -> &'static str {
        match self {
            Self::CommandExecution => "Codex command execution",
            Self::FileChange => "Codex file change",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ProviderApprovalDecision {
    Approved,
    Denied,
    Cancelled,
}

#[derive(Debug)]
pub(crate) struct ProviderApprovalRequest {
    pub(crate) kind: ProviderApprovalKind,
    pub(crate) item_id: String,
    pub(crate) thread_id: Option<String>,
    pub(crate) turn_id: Option<String>,
    pub(crate) summary: String,
    pub(crate) details: Value,
    pub(crate) responder: oneshot::Sender<ProviderApprovalDecision>,
}

pub(crate) type ProviderApprovalSender = mpsc::UnboundedSender<ProviderApprovalRequest>;
