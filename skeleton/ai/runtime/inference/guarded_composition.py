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
    roundtrip: Callable[[str], tuple[Sequence[int], str]] | None = None
    attest_source: Callable[..., Any] | None = None
    review_async: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        if self.review_async is not None and not callable(self.review_async):
            raise ProviderPolicyError("protected local async review must be callable")
        if self.attest_source is not None and not callable(self.attest_source):
            raise ProviderPolicyError("protected local source attestation must be callable")
        if self.roundtrip is not None and not callable(self.roundtrip):
            raise ProviderPolicyError("protected local roundtrip must be callable")
        if not callable(getattr(self.snapshots, "resolve", None)):
            raise ProviderPolicyError("protected local deployment lacks trusted snapshot authority")
        for name in (
            "reviewer", "tokenize", "detokenize", "verify_native_tokenizer",
            "sampler_support", "projection_attestor",
        ):
            if not callable(getattr(self, name)):
                raise ProviderPolicyError("protected local deployment lacks " + name)


@dataclass(frozen=True, slots=True)
class ProtectedLocalComponentFactory:
    """Deployer-owned per-backend guard constructor.

    A registry must build components only after it has loaded the real model.
    The snapshot reader is independently supplied and may be rebound by the
    trusted server before loading any model; a result cannot replace it.
    """

    snapshots: TrustedSnapshotReader
    build: Callable[[Any, TrustedSnapshotReader], ProtectedLocalComponents]

    def __post_init__(self) -> None:
        if not callable(getattr(self.snapshots, "resolve", None)) or not callable(self.build):
            raise ProviderPolicyError("trusted local component factory is incomplete")

    def for_backend(self, backend: Any) -> ProtectedLocalComponents:
        try:
            components = self.build(backend, self.snapshots)
        except Exception:
            raise ProviderPolicyError("trusted local component factory rejected backend") from None
        if (type(components) is not ProtectedLocalComponents
                or components.snapshots is not self.snapshots):
            raise ProviderPolicyError("trusted local component factory changed snapshot authority")
        return components


def is_protected_component_source(value: object) -> bool:
    return type(value) in (ProtectedLocalComponents, ProtectedLocalComponentFactory)


def resolve_protected_components(
    source: ProtectedLocalComponents | ProtectedLocalComponentFactory, backend: Any,
) -> ProtectedLocalComponents:
    if type(source) is ProtectedLocalComponentFactory:
        return source.for_backend(backend)
    if type(source) is not ProtectedLocalComponents:
        raise ProviderPolicyError("trusted local protection dependencies are missing")
    return source


def compose_protected_local_adapter(
    engine: LocalInferenceEngine, *,
    components: ProtectedLocalComponents | ProtectedLocalComponentFactory,
    default_seed: int = 0, artifact_status: dict[str, object] | None = None,
    activation_gate: Any | None = None,
) -> LocalModelAdapter:
    """Fail closed unless one protected engine has an attested native tokenizer.

    The identity probe is an independently trusted callback. Its return alone
    is not cryptographic proof; deployments must bind the callback to the
    activated backend/tokenizer artifact and continuously verify identity.
    """
    if not isinstance(engine, LocalInferenceEngine) or not engine.require_guarded_context:
        raise ProviderPolicyError("protected deployment requires engine-level execution fencing")
    components = resolve_protected_components(components, engine.model)
    try:
        verified = components.verify_native_tokenizer(
            engine.model, components.tokenize, components.detokenize,
        )
    except Exception as exc:
        raise ProviderPolicyError("active model tokenizer verification unavailable") from exc
    if verified is not True:
        raise ProviderPolicyError("active model tokenizer identity was not verified")
    guard = GuardedLocalInference(
        engine, reviewer=components.reviewer, review_async=components.review_async,
        tokenize=components.tokenize,
        detokenize=components.detokenize,
        roundtrip=components.roundtrip,
        sampler_support=components.sampler_support,
        projection_attestor=components.projection_attestor,
        tokenizer_identity_attestor=lambda: components.verify_native_tokenizer(
            engine.model, components.tokenize, components.detokenize,
        ),
        require_token_echo=True,
        # Exact GGUF performs independently pinned whole-artifact reads and
        # native vocabulary subprocess calls, not only in-memory callbacks.
        # The outer serving deadline is still enforced at every phase.
        native_timeout_seconds=30.0 if getattr(engine.model, "requires_exact_guard_tokens", False) is True else 5.0,
    )
    service = CanonicalGuardedLocalService(
        guard, snapshots=components.snapshots, activation_gate=activation_gate,
        attest_source=components.attest_source,
    )
    return LocalModelAdapter(
        engine, default_seed=default_seed, artifact_status=artifact_status,
        guarded_service=service, require_guarded_inference=True,
    )
