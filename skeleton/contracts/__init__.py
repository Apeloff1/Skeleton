"""Shared contract primitives for automation control planes."""

from .canonical import (
    CanonicalContractError,
    CanonicalEnvelope,
    EvidenceRef,
    Identity,
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
