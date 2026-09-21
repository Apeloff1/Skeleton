"""Shared contract primitives for automation control planes."""

from .canonical import (
    CanonicalContractError,
    CanonicalEnvelope,
    EvidenceRef,
    Identity,
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
    "OperationContractError",
    "OperationEnvelope",
    "OperationState",
    "OperationTransitionError",
    "TERMINAL_OPERATION_STATES",
]
