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
    "BatchCompatibilityKey": (".batching", "BatchCompatibilityKey"),
    "BatchItem": (".batching", "BatchItem"),
    "BatchPlan": (".batching", "BatchPlan"),
    "ContinuousBatchScheduler": (".batching", "ContinuousBatchScheduler"),
    "verify_batch_membership": (".batching", "verify_batch_membership"),
    "SpeculativeCandidate": (".speculation", "SpeculativeCandidate"),
    "SpeculationDecision": (".speculation", "SpeculationDecision"),
    "assess_speculative_candidate": (".speculation", "assess_speculative_candidate"),
    "require_speculative_equivalence": (".speculation", "require_speculative_equivalence"),
}

__all__ = list(_LAZY_EXPORTS)


def _load_reviewed_export_owner(module_name: str):
    """Keep import side effects limited to explicitly reviewed modules."""
    if module_name == ".session":
        return import_module(".session", __name__)
    if module_name == ".provider_bridge":
        return import_module(".provider_bridge", __name__)
    if module_name == ".replay":
        return import_module(".replay", __name__)
    if module_name == ".async_runtime":
        return import_module(".async_runtime", __name__)
    if module_name == ".flgb_runtime":
        return import_module(".flgb_runtime", __name__)
    if module_name == ".batching":
        return import_module(".batching", __name__)
    if module_name == ".speculation":
        return import_module(".speculation", __name__)
    raise ImportError("unregistered lazy export owner")


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(_load_reviewed_export_owner(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
