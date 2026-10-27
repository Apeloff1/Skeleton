"""Explicit trusted composition for fail-closed local-model deployment.

This is an activation boundary, not a user-facing configuration format. The
application root must construct these dependencies from trusted authorities.
A backend tokenization verifier must validate that the supplied encode/decode
callbacks are the real active model's tokenizer (not a generic byte echo).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from skeleton.context.pre_delivery_guard import (
    BoundedAdversarialReviewer,
    GuardedLocalInference,
)
from skeleton.provider_runtime import ProviderPolicyError

from .guarded_service import CanonicalGuardedLocalService, TrustedSnapshotReader
from .local import LocalInferenceEngine, LocalModelAdapter


@dataclass(frozen=True, slots=True)
class ProtectedLocalComponents:
    """Trusted app-owned dependencies; model text cannot construct these."""

    snapshots: TrustedSnapshotReader
    reviewer: BoundedAdversarialReviewer
    tokenize: Callable[[str], Sequence[int]]
    detokenize: Callable[[Sequence[int]], str]
    verify_native_tokenizer: Callable[[Any, Callable[..., Any], Callable[..., Any]], bool]
    sampler_support: Callable[[Any, Any], bool]
    projection_attestor: Callable[[Any, str, str], bool]

    def __post_init__(self) -> None:
        if not callable(getattr(self.snapshots, "resolve", None)):
            raise ProviderPolicyError("protected local deployment lacks trusted snapshot authority")
        for name in (
            "reviewer", "tokenize", "detokenize", "verify_native_tokenizer",
            "sampler_support", "projection_attestor",
        ):
            if not callable(getattr(self, name)):
                raise ProviderPolicyError("protected local deployment lacks " + name)


def compose_protected_local_adapter(
    engine: LocalInferenceEngine, *, components: ProtectedLocalComponents,
    default_seed: int = 0, artifact_status: dict[str, object] | None = None,
) -> LocalModelAdapter:
    """Fail closed unless one protected engine has an attested native tokenizer.

    The identity probe is an independently trusted callback. Its return alone
    is not cryptographic proof; deployments must bind the callback to the
    activated backend/tokenizer artifact and continuously verify identity.
    """
    if not isinstance(engine, LocalInferenceEngine) or not engine.require_guarded_context:
        raise ProviderPolicyError("protected deployment requires engine-level execution fencing")
    if not isinstance(components, ProtectedLocalComponents):
        raise ProviderPolicyError("trusted local protection dependencies are missing")
    try:
        verified = components.verify_native_tokenizer(
            engine.model, components.tokenize, components.detokenize,
        )
    except Exception as exc:
        raise ProviderPolicyError("active model tokenizer verification unavailable") from exc
    if verified is not True:
        raise ProviderPolicyError("active model tokenizer identity was not verified")
    guard = GuardedLocalInference(
        engine, reviewer=components.reviewer,
        tokenize=components.tokenize,
        detokenize=components.detokenize,
        sampler_support=components.sampler_support,
        projection_attestor=components.projection_attestor,
        require_token_echo=True,
    )
    service = CanonicalGuardedLocalService(guard, snapshots=components.snapshots)
    return LocalModelAdapter(
        engine, default_seed=default_seed, artifact_status=artifact_status,
        guarded_service=service, require_guarded_inference=True,
    )
