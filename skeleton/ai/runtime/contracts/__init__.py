"""Shared contract primitives for automation control planes."""

from .canonical import (
    CanonicalContractError,
    CanonicalEnvelope,
    EvidenceRef,
    Identity,
)
from .context import (
    CONTEXT_SCHEMA_VERSION,
    ContextBudget,
    ContextContractError,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
    estimate_tokens,
)
from .conversation import (
    CONVERSATION_SCHEMA_VERSION,
    ConversationAuthorType,
    ConversationContractError,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from .operation import (
    OperationContractError,
    OperationEnvelope,
    OperationState,
    OperationTransitionError,
    TERMINAL_OPERATION_STATES,
)

__all__ = [
    "CanonicalContractError",
    "CanonicalEnvelope",
    "EvidenceRef",
    "Identity",
    "CONTEXT_SCHEMA_VERSION",
    "ContextBudget",
    "ContextContractError",
    "ContextEnvelope",
    "ContextKind",
    "ContextSegment",
    "ContextTrust",
    "context_digest_payload",
    "estimate_tokens",
    "CONVERSATION_SCHEMA_VERSION",
    "ConversationAuthorType",
    "ConversationContractError",
    "ConversationMessage",
    "ConversationThread",
    "ConversationThreadState",
    "OperationContractError",
    "OperationEnvelope",
    "OperationState",
    "OperationTransitionError",
    "TERMINAL_OPERATION_STATES",
]
