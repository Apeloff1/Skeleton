"""Provider-neutral inference namespace with lazy public exports."""
from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "InferenceContractError": (".session", "InferenceContractError"),
    "InferenceSession": (".session", "InferenceSession"),
    "InferenceUsage": (".session", "InferenceUsage"),
    "ModelRequest": (".session", "ModelRequest"),
    "ModelResult": (".session", "ModelResult"),
    "ModelStreamEvent": (".session", "ModelStreamEvent"),
    "MAX_ATTEMPTS": (".session", "MAX_ATTEMPTS"),
    "MAX_EVENTS": (".session", "MAX_EVENTS"),
    "consume_provider_deltas": (".provider_bridge", "consume_provider_deltas"),
    "finish_provider_response": (".provider_bridge", "finish_provider_response"),
    "provider_payload_digest": (".provider_bridge", "provider_payload_digest"),
    "record_provider_delta": (".provider_bridge", "record_provider_delta"),
    "terminate_provider_failure": (".provider_bridge", "terminate_provider_failure"),
    "InferenceReplay": (".replay", "InferenceReplay"),
    "verify_replay": (".replay", "verify_replay"),
    "consume_provider_stream": (".async_runtime", "consume_provider_stream"),
    "StreamBudgetExceeded": (".async_runtime", "StreamBudgetExceeded"),
    "StreamDeadlineExceeded": (".async_runtime", "StreamDeadlineExceeded"),
    "CancellationToken": (".flgb_runtime", "CancellationToken"),
    "CancelledError": (".flgb_runtime", "CancelledError"),
    "ConversationState": (".flgb_runtime", "ConversationState"),
    "ConversationTurn": (".flgb_runtime", "ConversationTurn"),
    "DeadlineBudget": (".flgb_runtime", "DeadlineBudget"),
    "DeadlineExceeded": (".flgb_runtime", "DeadlineExceeded"),
    "FailoverAttempt": (".flgb_runtime", "FailoverAttempt"),
    "FLGBInferenceError": (".flgb_runtime", "FLGBInferenceError"),
    "OperationEnvelope": (".flgb_runtime", "OperationEnvelope"),
    "ProviderCandidate": (".flgb_runtime", "ProviderCandidate"),
    "ProviderFailoverPlan": (".flgb_runtime", "ProviderFailoverPlan"),
    "ProviderNeutralRequest": (".flgb_runtime", "ProviderNeutralRequest"),
    "ReplayReceipt": (".flgb_runtime", "ReplayReceipt"),
    "StreamDecoder": (".flgb_runtime", "StreamDecoder"),
    "TerminalCommitReceipt": (".flgb_runtime", "TerminalCommitReceipt"),
    "ToolCallProposal": (".flgb_runtime", "ToolCallProposal"),
    "UsageEntry": (".flgb_runtime", "UsageEntry"),
    "UsageLedger": (".flgb_runtime", "UsageLedger"),
    "parse_structured_output": (".flgb_runtime", "parse_structured_output"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
