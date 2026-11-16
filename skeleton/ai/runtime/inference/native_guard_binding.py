"""Artifact-bound native transformer guard construction.

A trusted application can call this only after constructing the actual native
model. Unlike caller-supplied callback assertions, identity is tied to the
active backend and to its real admitted NativeTokenizer methods and digests.
Non-invertible tokenizer mappings still fail closed per prompt in preflight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.context.pre_delivery_guard import BoundedAdversarialReviewer
from skeleton.provider_runtime import ProviderPolicyError

from .guarded_composition import ProtectedLocalComponents, ProtectedLocalComponentFactory
from .guarded_service import TrustedSnapshotReader
from .native_transformer import NativeTransformerModel


def native_transformer_guard_components(
    backend: NativeTransformerModel, *,
    snapshots: TrustedSnapshotReader,
    reviewer: BoundedAdversarialReviewer,
) -> ProtectedLocalComponents:
    """Bind a real native tokenizer to one immutable backend instance.

    The snapshot authority and independently administered reviewer must come
    from the trusted application startup, not from generated model content.
    """
    if type(backend) is not NativeTransformerModel:
        raise ProviderPolicyError("native guarded activation requires the exact transformer backend")
    return _exact_native_components(backend, snapshots=snapshots, reviewer=reviewer)


def _exact_native_components(
    backend: Any, *, snapshots: TrustedSnapshotReader, reviewer: BoundedAdversarialReviewer,
) -> ProtectedLocalComponents:
    if not callable(getattr(snapshots, "resolve", None)) or not callable(reviewer):
        raise ProviderPolicyError("native guarded activation requires application-owned authorities")
    try:
        backend.assert_identity()
        tokenizer = backend.runtime.tokenizer
        tokenizer.assert_unchanged()
        identity = (backend.model_digest, backend.runtime_digest, tokenizer.digest)
        if any(not isinstance(value, str) or len(value) != 64
               or any(ch not in "0123456789abcdef" for ch in value)
               for value in identity):
            raise ProviderPolicyError("native tokenizer has invalid admitted identity")
        encode = tokenizer.encode_ids
        decode = tokenizer.decode_ids
    except Exception as exc:
        raise ProviderPolicyError("native tokenizer identity admission unavailable") from exc

    def verify(active_backend: Any, encoder: Any, decoder: Any) -> bool:
        # Compare exact bound function objects captured at activation; a
        # different backend or a different callback can never be substituted.
        if active_backend is not backend or encoder is not encode or decoder is not decode:
            return False
        try:
            backend.assert_identity()
            tokenizer.assert_unchanged()
            if backend.runtime.tokenizer is not tokenizer:
                return False
            return (backend.model_digest, backend.runtime_digest, tokenizer.digest) == identity
        except Exception:
            return False

    return ProtectedLocalComponents(
        snapshots=snapshots,
        reviewer=reviewer,
        tokenize=encode,
        detokenize=decode,
        verify_native_tokenizer=verify,
        # The native transformer currently advertises text generation only.
        sampler_support=lambda active, contract: False,
        # The native transformer uses the canonical LocalInferenceRequest
        # renderer. No alternate prompt projection is implicitly attested.
        projection_attestor=lambda request, text, root: False,
    )


@dataclass(frozen=True, slots=True)
class NativeGuardPins:
    """Independently reviewed identity for one loaded native model."""
    model_id: str
    model_digest: str
    runtime_digest: str
    tokenizer_digest: str

    def __post_init__(self) -> None:
        if (type(self.model_id) is not str or not 1 <= len(self.model_id) <= 256
                or self.model_id != self.model_id.strip()
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in self.model_id)):
            raise ProviderPolicyError("native guard model pin invalid")
        for digest in (self.model_digest, self.runtime_digest, self.tokenizer_digest):
            if (type(digest) is not str or len(digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in digest)):
                raise ProviderPolicyError("native guard artifact pin invalid")


def make_pinned_native_guard_factory(
    *, snapshots: TrustedSnapshotReader, reviewer: Any,
    pins: tuple[NativeGuardPins, ...],
) -> ProtectedLocalComponentFactory:
    """Bind each eligible native backend created by the actual provider registry.

    No generic tokenizer, GGUF CLI byte estimate or unsupported artifact is
    treated as native evidence. Pins are independent deployment inputs;
    they must not be derived from whatever model happened to load.
    """
    from .native_runtime import NativeRuntimeLocalModel
    from .gguf_token_bridge import GgufTokenBridgeModel
    from .signed_reviewer_client import SignedReviewerClient
    from .reviewer_custody import ReviewerTrustAnchor
    if (type(reviewer) is not SignedReviewerClient
            or type(getattr(reviewer, "_anchor", None)) is not ReviewerTrustAnchor):
        raise ProviderPolicyError("pinned independent reviewer required")
    anchor = reviewer._anchor
    if (type(pins) is not tuple or not 1 <= len(pins) <= 32
            or any(type(pin) is not NativeGuardPins for pin in pins)):
        raise ProviderPolicyError("native guard pin inventory invalid")
    by_id = {pin.model_id: pin for pin in pins}
    if len(by_id) != len(pins):
        raise ProviderPolicyError("duplicate native guard model pins")

    def build(backend: Any, reader: TrustedSnapshotReader) -> ProtectedLocalComponents:
        if type(backend) not in (NativeTransformerModel, NativeRuntimeLocalModel, GgufTokenBridgeModel):
            raise ProviderPolicyError("loaded backend lacks admitted exact native tokenizer")
        if type(getattr(backend, "model_id", None)) is not str:
            raise ProviderPolicyError("native guard model identity invalid")
        pin = by_id.get(backend.model_id)
        if pin is None or reviewer._anchor != anchor:
            raise ProviderPolicyError("native guard model or reviewer pin unavailable")
        if type(backend) is GgufTokenBridgeModel:
            backend.assert_identity()
            encode, decode = backend.encode_ids, backend.decode_ids

            def bridge_verify(active, encoder, decoder):
                if active is not backend or encoder is not encode or decoder is not decode:
                    return False
                try:
                    backend.assert_identity()
                    return (getattr(backend.encode_ids, "__func__", None) is getattr(encode, "__func__", None)
                            and getattr(backend.decode_ids, "__func__", None) is getattr(decode, "__func__", None))
                except Exception:
                    return False

            components = ProtectedLocalComponents(
                snapshots=reader, reviewer=reviewer, tokenize=encode, detokenize=decode,
                verify_native_tokenizer=bridge_verify,
                sampler_support=lambda *_: False, projection_attestor=lambda *_: False,
            )
            get_tokenizer_digest = lambda: backend.tokenizer_digest
        else:
            components = _exact_native_components(backend, snapshots=reader, reviewer=reviewer)
            get_tokenizer_digest = lambda: backend.runtime.tokenizer.digest
        expected = (pin.model_digest, pin.runtime_digest, pin.tokenizer_digest)
        try:
            observed = (backend.model_digest, backend.runtime_digest, get_tokenizer_digest())
            if observed != expected:
                raise ProviderPolicyError("loaded native backend differs from operator pins")
        except Exception:
            raise ProviderPolicyError("loaded native backend differs from operator pins") from None
        from dataclasses import replace
        verify = components.verify_native_tokenizer

        def pinned_verifier(active: Any, encoder: Any, decoder: Any) -> bool:
            try:
                return (reviewer._anchor == anchor
                        and backend.model_id == pin.model_id
                        and verify(active, encoder, decoder)
                        and (backend.model_digest, backend.runtime_digest,
                             get_tokenizer_digest()) == expected)
            except Exception:
                return False

        return replace(components, verify_native_tokenizer=pinned_verifier)

    return ProtectedLocalComponentFactory(snapshots=snapshots, build=build)


def build_guarded_native_transformer_adapter(
    runtime: Any, *,
    snapshots: TrustedSnapshotReader,
    reviewer: BoundedAdversarialReviewer,
    **adapter_options: Any,
):
    """Construct backend, then bind its exact native tokenizer at startup.

    No generic user-supplied true-returning attestor is required, and no
    unguarded adapter is created on any failure.
    """
    if "guarded_components" in adapter_options or "guarded_components_factory" in adapter_options:
        raise ProviderPolicyError("native guard composition cannot be replaced by caller options")
    if "require_guarded_inference" in adapter_options:
        raise ProviderPolicyError("native guard policy is mandatory in this factory")
    from .native_transformer import build_native_transformer_adapter
    return build_native_transformer_adapter(
        runtime, require_guarded_inference=True,
        guarded_components_factory=lambda backend: native_transformer_guard_components(
            backend, snapshots=snapshots, reviewer=reviewer,
        ),
        **adapter_options,
    )


__all__ = ["native_transformer_guard_components", "build_guarded_native_transformer_adapter",
           "NativeGuardPins", "make_pinned_native_guard_factory"]
