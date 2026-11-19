"""Non-owning import alias for the canonical local readiness gate."""
from skeleton.provider_model_readiness import (
    EnvelopedLocalReadyAdapter,
    InvocationBudget,
    LOCAL_NATIVE_PROVIDER_IDS,
    LocalModelReadinessGate,
    LocalReadyProviderAdapter,
    ResourceEnvelope,
    ResourceEnvelopeExhausted,
    invoke_bounded,
    run_bounded_loop,
)

__all__ = [
    "EnvelopedLocalReadyAdapter",
    "InvocationBudget",
    "LOCAL_NATIVE_PROVIDER_IDS",
    "LocalModelReadinessGate",
    "LocalReadyProviderAdapter",
    "ResourceEnvelope",
    "ResourceEnvelopeExhausted",
    "invoke_bounded",
    "run_bounded_loop",
]
