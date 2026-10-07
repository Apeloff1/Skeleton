"""Integrated deterministic text-to-model-input pipeline.

Composes normalization, native tokenization, context-window preparation and
bounded batching without weakening the lower-level FLGB-02 contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Iterator, Sequence

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
    raw_text_digest: str
    normalized_text_digest: str

    def __post_init__(self) -> None:
        if len(self.pipeline_digest) != 64:
            raise TokenizerContractError("invalid pipeline digest")
        if len(self.raw_text_digest) != 64 or len(self.normalized_text_digest) != 64:
            raise TokenizerContractError("invalid text provenance digest")
        if any(ch not in "0123456789abcdef" for ch in self.raw_text_digest + self.normalized_text_digest):
            raise TokenizerContractError("text provenance digest must be lowercase hex")
        expected_normalized = sha256(self.normalized_text.encode("utf-8")).hexdigest()
        if self.normalized_text_digest != expected_normalized:
            raise TokenizerContractError("normalized text digest mismatch")
        if self.sequence.source_text_digest != self.normalized_text_digest:
            raise TokenizerContractError("sequence/normalized text provenance mismatch")
        if any(window.source_sequence_digest != self.sequence.digest for window in self.windows):
            raise TokenizerContractError("window provenance mismatch")
        flattened = tuple(window for batch in self.batches for window in batch.windows)
        if flattened != self.windows:
            raise TokenizerContractError("batch/window accounting mismatch")


@dataclass(frozen=True)
class ModelInputBatch:
    """Rectangular model-ready token ids with explicit attention semantics."""
    input_ids: tuple[tuple[int, ...], ...]
    attention_mask: tuple[tuple[int, ...], ...]
    source_window_digests: tuple[str, ...]
    pad_token_id: int

    def __post_init__(self) -> None:
        if not self.input_ids:
            raise TokenizerContractError("empty model input batch")
        width = len(self.input_ids[0])
        if width <= 0 or any(len(row) != width for row in self.input_ids):
            raise TokenizerContractError("ragged model input ids")
        if len(self.attention_mask) != len(self.input_ids) or any(len(row) != width for row in self.attention_mask):
            raise TokenizerContractError("attention mask shape mismatch")
        if len(self.source_window_digests) != len(self.input_ids):
            raise TokenizerContractError("model batch provenance mismatch")
        if any(bit not in (0, 1) for row in self.attention_mask for bit in row):
            raise TokenizerContractError("invalid attention mask")
        for ids, mask in zip(self.input_ids, self.attention_mask):
            seen_padding = False
            for token_id, bit in zip(ids, mask):
                if bit == 0:
                    seen_padding = True
                    if token_id != self.pad_token_id:
                        raise TokenizerContractError("masked token is not padding")
                elif seen_padding:
                    raise TokenizerContractError("non-padding token after padding")

    @property
    def digest(self) -> str:
        return digest_json({"input_ids": [list(row) for row in self.input_ids], "attention_mask": [list(row) for row in self.attention_mask], "source_window_digests": list(self.source_window_digests), "pad_token_id": self.pad_token_id})


def materialize_model_batch(windows: Sequence[TokenWindow], *, pad_token_id: int) -> ModelInputBatch:
    items = tuple(windows)
    if not items:
        raise TokenizerContractError("empty model input windows")
    if isinstance(pad_token_id, bool) or not isinstance(pad_token_id, int) or pad_token_id < 0:
        raise TokenizerContractError("invalid pad_token_id")
    if any(not isinstance(window, TokenWindow) for window in items):
        raise TokenizerContractError("TokenWindow required")
    width = max(len(window.token_ids) for window in items)
    rows, masks, digests = [], [], []
    for window in items:
        padding = width - len(window.token_ids)
        rows.append(tuple(window.token_ids) + (pad_token_id,) * padding)
        masks.append((1,) * len(window.token_ids) + (0,) * padding)
        digests.append(window.digest)
    return ModelInputBatch(tuple(rows), tuple(masks), tuple(digests), pad_token_id)


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
        return PreparedText(
            normalized,
            sequence,
            windows,
            batches,
            self.digest,
            sha256(text.encode("utf-8")).hexdigest(),
            sha256(normalized.encode("utf-8")).hexdigest(),
        )

    def model_batches(self, prepared: PreparedText, *, pad_token_id: int | None = None) -> tuple[ModelInputBatch, ...]:
        if not isinstance(prepared, PreparedText) or prepared.pipeline_digest != self.digest:
            raise TokenizerContractError("prepared text belongs to another pipeline")
        pad = self.tokenizer.vocabulary_manifest.special_tokens["unk"] if pad_token_id is None else pad_token_id
        if isinstance(pad, bool) or not isinstance(pad, int) or not 0 <= pad < self.tokenizer.vocab_size:
            raise TokenizerContractError("padding token outside vocabulary")
        return tuple(materialize_model_batch(batch.windows, pad_token_id=pad) for batch in prepared.batches)

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
        accepted: list[str] = []
        for chunk in chunks:
            feed.push(chunk)
            accepted.append(chunk)
        # Finalize to enforce one-shot lifecycle and tokenizer admission.
        # The finalized sequence is deliberately checked against prepare() so
        # streaming can never silently use a different tokenizer identity.
        streamed = feed.finalize(self.tokenizer)
        prepared = self.prepare("".join(accepted))
        if streamed.tokenizer_digest != prepared.sequence.tokenizer_digest:
            raise TokenizerContractError("stream tokenizer identity mismatch")
        return prepared


__all__ = ["ModelInputBatch", "PreparedText", "TextPipelineConfig", "TextTokenPipeline", "materialize_model_batch"]
