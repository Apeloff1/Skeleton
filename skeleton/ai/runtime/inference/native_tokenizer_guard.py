"""Actual native-transformer tokenizer binding for protected local inference.

An app owner supplies the authorized canonical snapshot reader and independent
reviewer; this helper only binds encode/decode and attestation to the *same*
activated NativeLLMRuntime. No fabricated tokenizer echo or assumed GGUF
command-line tokenizer interface is used.
"""

from __future__ import annotations

from typing import Any

from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.tokenization import NativeTokenizer
from skeleton.provider_runtime import ProviderPolicyError

from .guarded_composition import ProtectedLocalComponents
from .native_transformer import NativeTransformerModel


def bind_native_transformer_guard(
    runtime: NativeLLMRuntime, *, snapshots: Any, reviewer: Any,
) -> ProtectedLocalComponents:
    """Create fail-closed dependencies bound to a specific native tokenizer.

    Real authorization and the reviewer remain operator-owned. Native tokens
    must have a byte-preserving round-trip for the admitted prompt; if a
    tokenizer cannot represent the prompt exactly, delivery fails before model
    inference. Native structured-output grammar is currently unsupported.
    """
    if not isinstance(runtime, NativeLLMRuntime):
        raise ProviderPolicyError("native guard requires activated NativeLLMRuntime")
    tokenizer = runtime.tokenizer
    if not isinstance(tokenizer, NativeTokenizer):
        raise ProviderPolicyError("native guard requires the owned tokenizer")
    tokenizer.assert_unchanged()
    pinned_digest = tokenizer.digest
    if (not isinstance(pinned_digest, str) or len(pinned_digest) != 64
            or any(character not in "0123456789abcdef" for character in pinned_digest)):
        raise ProviderPolicyError("native tokenizer digest pin is invalid")
    # Bound callable instances: no caller-provided tokenizer proxy may silently
    # substitute a generic byte codec or another model's vocabulary.
    encode = tokenizer.encode_ids
    decode = tokenizer.decode_ids

    def verify_native_tokenizer(model: Any, admitted_encode: Any, admitted_decode: Any) -> bool:
        if not isinstance(model, NativeTransformerModel):
            return False
        if model.runtime is not runtime or runtime.tokenizer is not tokenizer:
            return False
        if (admitted_encode is not encode or admitted_decode is not decode
                or getattr(admitted_encode, "__self__", None) is not tokenizer
                or getattr(admitted_decode, "__self__", None) is not tokenizer):
            return False
        try:
            tokenizer.assert_unchanged()
            model._assert_identity()
        except Exception:
            return False
        return tokenizer.digest == pinned_digest and model._tokenizer_digest == pinned_digest

    return ProtectedLocalComponents(
        snapshots=snapshots, reviewer=reviewer,
        tokenize=encode, detokenize=decode,
        verify_native_tokenizer=verify_native_tokenizer,
        sampler_support=lambda _model, _contract: False,
        projection_attestor=lambda _request, _rendered, _root: False,
    )


__all__ = ["bind_native_transformer_guard"]
