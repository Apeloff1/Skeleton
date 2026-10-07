"""Integrated deterministic text-to-model-input pipeline.

Composes normalization, native tokenization, context-window preparation and
bounded batching without weakening the lower-level FLGB-02 contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Iterator

from .flgb_model_runtime import TokenSequence, digest_json
from .text_normalization import normalize_text
from .tokenization import (
    NativeTokenizer, StreamingTextFeed, TokenBatch, TokenWindow,
    TokenizerContractError, batch_token_windows, iter_context_windows,
)


@dataclass(frozen=True)
class TextPipelineConfig:
    normalization: str = "NFC"
    context_size: int = 4096
    stride: int | None = None
    include_tail: bool = True
    max_batch_size: int = 32
    max_tokens_per_batch: int = 131072

    def __post_init__(self) -> None:
        if self.normalization not in {"NONE", "NFC", "NFD", "NFKC", "NFKD"}:
            raise TokenizerContractError("unsupported normalization")
        if isinstance(self.context_size, bool) or not isinstance(self.context_size, int) or self.context_size <= 0:
            raise TokenizerContractError("invalid context_size")
        if self.stride is not None and (
            isinstance(self.stride, bool) or not isinstance(self.stride, int)
            or self.stride <= 0 or self.stride > self.context_size
        ):
            raise TokenizerContractError("invalid stride")
        if isinstance(self.max_batch_size, bool) or not isinstance(self.max_batch_size, int) or self.max_batch_size <= 0:
            raise TokenizerContractError("invalid max_batch_size")
        if isinstance(self.max_tokens_per_batch, bool) or not isinstance(self.max_tokens_per_batch, int) or self.max_tokens_per_batch <= 0:
            raise TokenizerContractError("invalid max_tokens_per_batch")

    @property
    def digest(self) -> str:
        return digest_json({
            "normalization": self.normalization,
            "context_size": self.context_size,
            "stride": self.stride,
            "include_tail": self.include_tail,
            "max_batch_size": self.max_batch_size,
            "max_tokens_per_batch": self.max_tokens_per_batch,
        })


@dataclass(frozen=True)
class PreparedText:
    normalized_text: str
    sequence: TokenSequence
    windows: tuple[TokenWindow, ...]
    batches: tuple[TokenBatch, ...]
    pipeline_digest: str

    def __post_init__(self) -> None:
        if len(self.pipeline_digest) != 64:
            raise TokenizerContractError("invalid pipeline digest")
        if any(window.source_sequence_digest != self.sequence.digest for window in self.windows):
            raise TokenizerContractError("window provenance mismatch")
        flattened = tuple(window for batch in self.batches for window in batch.windows)
        if flattened != self.windows:
            raise TokenizerContractError("batch/window accounting mismatch")


class TextTokenPipeline:
    """One admitted, immutable text-to-model-input pipeline."""

    SCHEMA = "skeleton.ai.text-token-pipeline.v1"

    def __init__(self, tokenizer: NativeTokenizer, config: TextPipelineConfig | None = None) -> None:
        if not isinstance(tokenizer, NativeTokenizer):
            raise TokenizerContractError("NativeTokenizer required")
        self.tokenizer = tokenizer
        self.config = config or TextPipelineConfig()
        self._digest = digest_json({
            "schema": self.SCHEMA,
            "tokenizer_digest": tokenizer.digest,
            "config_digest": self.config.digest,
        })

    @property
    def digest(self) -> str:
        return self._digest

    def normalize(self, text: str) -> str:
        value = normalize_text(text, self.config.normalization)
        if len(value) > self.tokenizer.limits.max_chars:
            raise TokenizerContractError("normalized text character budget exceeded")
        return value

    def encode(self, text: str) -> TokenSequence:
        self.tokenizer.assert_unchanged()
        return self.tokenizer.encode_sequence(self.normalize(text))

    def prepare(self, text: str) -> PreparedText:
        normalized = self.normalize(text)
        self.tokenizer.assert_unchanged()
        sequence = self.tokenizer.encode_sequence(normalized)
        windows = tuple(iter_context_windows(
            sequence,
            context_size=self.config.context_size,
            stride=self.config.stride,
            include_tail=self.config.include_tail,
        ))
        batches = batch_token_windows(
            windows,
            max_batch_size=self.config.max_batch_size,
            max_tokens_per_batch=self.config.max_tokens_per_batch,
        ) if windows else ()
        return PreparedText(normalized, sequence, windows, batches, self.digest)

    def decode(self, sequence: TokenSequence, *, require_identity: bool = True) -> str:
        if not isinstance(sequence, TokenSequence):
            raise TokenizerContractError("TokenSequence required")
        self.tokenizer.assert_unchanged()
        if require_identity and sequence.tokenizer_digest != self.tokenizer.digest:
            raise TokenizerContractError("tokenizer identity mismatch")
        return self.tokenizer.decode_ids(sequence.token_ids)

    def verify_round_trip(self, text: str) -> TokenSequence:
        normalized = self.normalize(text)
        sequence = self.tokenizer.encode_sequence(normalized)
        decoded = self.decode(sequence)
        # Not every admitted legacy vocabulary is lossless. Never pretend it is.
        # Where decoding is lossless, bind the exact normalized source digest.
        if decoded == normalized:
            expected = sha256(normalized.encode("utf-8")).hexdigest()
            if sequence.source_text_digest != expected:
                raise TokenizerContractError("source digest mismatch")
        return sequence

    def stream(self, chunks: Iterable[str]) -> PreparedText:
        # Normalize only after assembly: Unicode composition and CRLF boundaries
        # can straddle arbitrary transport chunks.
        feed = StreamingTextFeed(limits=self.tokenizer.limits)
        for chunk in chunks:
            feed.push(chunk)
        raw = "".join(feed._chunks)
        feed._closed = True
        return self.prepare(raw)


__all__ = ["PreparedText", "TextPipelineConfig", "TextTokenPipeline"]
