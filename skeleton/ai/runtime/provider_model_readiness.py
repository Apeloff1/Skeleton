"""Non-owning import alias for the canonical local readiness gate."""
from skeleton.provider_model_readiness import (
    EnvelopedLocalReadyAdapter,
    LOCAL_NATIVE_PROVIDER_IDS,
    LocalModelReadinessGate,
    LocalReadyProviderAdapter,
    ResourceEnvelope,
)

__all__ = [
    "EnvelopedLocalReadyAdapter",
    "LOCAL_NATIVE_PROVIDER_IDS",
    "LocalModelReadinessGate",
    "LocalReadyProviderAdapter",
    "ResourceEnvelope",
]
