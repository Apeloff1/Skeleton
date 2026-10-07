from __future__ import annotations

import pytest

from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig
from skeleton.ai.model_runtime.tokenization import TokenizerContractError


def test_pipeline_config_digest_is_deterministic():
    left = TextPipelineConfig(context_size=128, stride=64, max_batch_size=4, max_tokens_per_batch=512)
    right = TextPipelineConfig(context_size=128, stride=64, max_batch_size=4, max_tokens_per_batch=512)
    assert left.digest == right.digest
    assert len(left.digest) == 64


@pytest.mark.parametrize("kwargs", [
    {"normalization": "BOGUS"},
    {"context_size": 0},
    {"context_size": True},
    {"context_size": 8, "stride": 9},
    {"context_size": 8, "stride": 0},
    {"max_batch_size": 0},
    {"max_tokens_per_batch": 0},
])
def test_pipeline_config_fails_closed(kwargs):
    with pytest.raises(TokenizerContractError):
        TextPipelineConfig(**kwargs)


def test_normalization_is_provenance_visible_in_sequence_digest(native_model):
    """Byte-distinct source text must not silently collapse provenance."""
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    raw = "Cafe\u0301"
    prepared = pipeline.prepare(raw)

    raw_digest = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()
    normalized_digest = __import__("hashlib").sha256(prepared.normalized_text.encode("utf-8")).hexdigest()
    assert prepared.normalized_text == "Caf\u00e9"
    assert prepared.raw_text_digest == raw_digest
    assert prepared.normalized_text_digest == normalized_digest
    assert prepared.raw_text_digest != prepared.normalized_text_digest
    assert prepared.sequence.source_text_digest == prepared.normalized_text_digest


def test_pipeline_digest_binds_normalization_policy(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    tokenizer = NativeTokenizer(native_model)
    nfc = TextTokenPipeline(tokenizer, TextPipelineConfig(normalization="NFC"))
    none = TextTokenPipeline(tokenizer, TextPipelineConfig(normalization="NONE"))

    assert nfc.digest != none.digest


def test_prepared_text_rejects_tampered_provenance(native_model):
    from dataclasses import replace
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError

    prepared = TextTokenPipeline(NativeTokenizer(native_model)).prepare("alpha")
    with pytest.raises(TokenizerContractError):
        replace(prepared, raw_text_digest="0" * 63)
    with pytest.raises(TokenizerContractError):
        replace(prepared, normalized_text_digest="0" * 64)


def test_stream_preserves_raw_chunk_boundary_independent_provenance(native_model):
    import hashlib
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    raw = "Cafe\u0301\r\nnext"
    one = pipeline.stream([raw])
    split = pipeline.stream(["Ca", "fe\u0301\r", "\nnext"])

    assert one.raw_text_digest == split.raw_text_digest == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert one.normalized_text_digest == split.normalized_text_digest
    assert one.sequence.digest == split.sequence.digest
    assert one.pipeline_digest == split.pipeline_digest
