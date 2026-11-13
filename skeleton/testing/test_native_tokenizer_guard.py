"""Native tokenizer identity must come from the actual activated model."""

from __future__ import annotations

from hashlib import sha256

import pytest

from skeleton.ai.runtime.inference.native_tokenizer_guard import bind_native_transformer_guard
from skeleton.ai.runtime.inference.native_transformer import NativeTransformerModel
from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.context.pre_delivery_guard import ReviewVerdict
from skeleton.cortex.transformer import TinyTransformer
from skeleton.provider_runtime import ProviderPolicyError


class Reader:
    async def resolve(self, **kwargs):
        raise AssertionError("snapshot resolution does not occur at tokenizer activation")


def independent_review(text, digest):
    return ReviewVerdict(True, digest, "independent-reviewer", "allow")


def runtime():
    return NativeLLMRuntime(TinyTransformer(
        vocab=("system", "user", "assistant", "hello", "world", ":"),
        dim=8, ctx=64, seed=41,
    ))


def test_native_guard_binds_real_runtime_and_tokenizer_callables():
    active = runtime()
    components = bind_native_transformer_guard(
        active, snapshots=Reader(), reviewer=independent_review,
    )
    model = NativeTransformerModel(active)
    assert components.tokenize.__self__ is active.tokenizer
    assert components.detokenize.__self__ is active.tokenizer
    assert components.verify_native_tokenizer(
        model, components.tokenize, components.detokenize,
    ) is True
    assert components.sampler_support(model, object()) is False
    assert components.projection_attestor(object(), "", "") is False


def test_runtime_and_function_substitution_refused():
    active = runtime()
    foreign = runtime()
    components = bind_native_transformer_guard(
        active, snapshots=Reader(), reviewer=independent_review,
    )
    wrong_model = NativeTransformerModel(foreign)
    assert components.verify_native_tokenizer(
        wrong_model, components.tokenize, components.detokenize,
    ) is False
    original = NativeTransformerModel(active)
    assert components.verify_native_tokenizer(
        original, foreign.tokenizer.encode_ids, components.detokenize,
    ) is False
    assert components.verify_native_tokenizer(
        original, components.tokenize, foreign.tokenizer.decode_ids,
    ) is False
    assert components.verify_native_tokenizer(
        object(), components.tokenize, components.detokenize,
    ) is False


def test_tokenizer_digest_drift_fails_closed():
    active = runtime()
    components = bind_native_transformer_guard(
        active, snapshots=Reader(), reviewer=independent_review,
    )
    model = NativeTransformerModel(active)
    active.tokenizer._digest = "0" * 64
    assert components.verify_native_tokenizer(
        model, components.tokenize, components.detokenize,
    ) is False


def test_cannot_bind_unknown_runtime_or_claim_generic_byte_tokenizer():
    with pytest.raises(ProviderPolicyError, match="NativeLLMRuntime"):
        bind_native_transformer_guard(
            object(), snapshots=Reader(), reviewer=independent_review,
        )


def test_native_codec_roundtrip_is_not_assumed_for_unknown_tokens():
    active = runtime()
    components = bind_native_transformer_guard(
        active, snapshots=Reader(), reviewer=independent_review,
    )
    sample = "a very unfamiliar character sequence xyzzy"
    encoded = components.tokenize(sample)
    assert isinstance(encoded, tuple)
    # Unknown vocab tokens are allowed to be lossy in model semantics;
    # the pre-delivery guard itself rejects any nonidentical byte echo.
    assert components.detokenize(encoded) != sample
