"""Artifact-bound native transformer guard construction.

A trusted application can call this only after constructing the actual native
model. Unlike caller-supplied callback assertions, identity is tied to the
active backend and to its real admitted NativeTokenizer methods and digests.
Non-invertible tokenizer mappings still fail closed per prompt in preflight.
"""

from __future__ import annotations

from typing import Any

from skeleton.context.pre_delivery_guard import BoundedAdversarialReviewer
from skeleton.provider_runtime import ProviderPolicyError

from .guarded_composition import ProtectedLocalComponents
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


__all__ = ["native_transformer_guard_components"]
