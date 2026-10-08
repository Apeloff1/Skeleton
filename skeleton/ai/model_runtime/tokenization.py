"""Deterministic text-to-token ingestion for the native FLGB-02 runtime."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Iterator, Mapping, Sequence

from skeleton.cortex.transformer import TinyTransformer, UNK

from .flgb_model_runtime import (
    MAX_TOKENS,
    ModelRuntimeError,
    TokenSequence,
    VocabularyManifest,
    canonical_bytes,
    digest_json,
)

MAX_TEXT_CHARS = 16_000_000
MAX_TEXT_CHUNKS = 65_536
MAX_CHUNK_CHARS = 1_000_000
MAX_SERIALIZED_SEQUENCE_BYTES = 32_000_000


class TokenizerContractError(ModelRuntimeError):
    """Fail-closed text/token pipeline contract violation."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive(value: Any, name: str, upper: int) -> int:
    if not _is_int(value) or not 1 <= value <= upper:
        raise TokenizerContractError(f"invalid {name}")
    return int(value)


@dataclass(frozen=True)
class TokenizerLimits:
    max_chars: int = MAX_TEXT_CHARS
    max_chunks: int = MAX_TEXT_CHUNKS
    max_chunk_chars: int = MAX_CHUNK_CHARS
    max_tokens: int = MAX_TOKENS

    def __post_init__(self) -> None:
        _positive(self.max_chars, "max_chars", MAX_TEXT_CHARS)
        _positive(self.max_chunks, "max_chunks", MAX_TEXT_CHUNKS)
        _positive(self.max_chunk_chars, "max_chunk_chars", MAX_CHUNK_CHARS)
        _positive(self.max_tokens, "max_tokens", MAX_TOKENS)
        if self.max_chunk_chars > self.max_chars:
            raise TokenizerContractError("chunk budget exceeds text budget")


@dataclass(frozen=True)
class TokenWindow:
    start: int
    stop: int
    token_ids: tuple[int, ...]
    source_sequence_digest: str

    def __post_init__(self) -> None:
        if not _is_int(self.start) or not _is_int(self.stop) or self.start < 0 or self.stop <= self.start:
            raise TokenizerContractError("invalid token window range")
        if self.stop - self.start != len(self.token_ids):
            raise TokenizerContractError("token window range/content mismatch")
        if len(self.source_sequence_digest) != 64:
            raise TokenizerContractError("invalid source sequence digest")
        for token_id in self.token_ids:
            if not _is_int(token_id) or not 0 <= token_id < 2**31:
                raise TokenizerContractError("invalid token window id")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "start": self.start,
                "stop": self.stop,
                "token_ids": list(self.token_ids),
                "source_sequence_digest": self.source_sequence_digest,
            }
        )


@dataclass(frozen=True)
class TokenBatch:
    windows: tuple[TokenWindow, ...]
    total_tokens: int

    def __post_init__(self) -> None:
        if not self.windows:
            raise TokenizerContractError("empty token batch")
        observed = sum(len(window.token_ids) for window in self.windows)
        if self.total_tokens != observed:
            raise TokenizerContractError("token batch accounting mismatch")


class NativeTokenizer:
    """Stable tokenizer identity bound to one native transformer vocabulary."""

    SCHEMA = "skeleton.ai.native-tokenizer.v1"

    def __init__(self, model: TinyTransformer, *, limits: TokenizerLimits | None = None) -> None:
        if not isinstance(model, TinyTransformer):
            raise TokenizerContractError("TinyTransformer required")
        self.model = model
        self.limits = limits or TokenizerLimits()
        self._vocab = tuple(str(token) for token in model.itos)
        if not self._vocab or len(set(self._vocab)) != len(self._vocab):
            raise TokenizerContractError("model vocabulary must be non-empty and unique")
        if len(model.E) != len(self._vocab):
            raise TokenizerContractError("model embedding/vocabulary size mismatch")
        if not _is_int(model.unk) or not 0 <= model.unk < len(self._vocab):
            raise TokenizerContractError("invalid model unknown-token id")
        declared_specials = {"unk": int(model.unk)}
        for name in ("pad", "bos", "eos"):
            attr = getattr(model, name, None)
            if attr is None:
                continue
            if not _is_int(attr) or not 0 <= attr < len(self._vocab):
                raise TokenizerContractError(f"invalid model {name}-token id")
            declared_specials[name] = int(attr)
        if len(set(declared_specials.values())) != len(declared_specials):
            raise TokenizerContractError("special token ids must be distinct")
        self._manifest = VocabularyManifest(
            "native-transformer",
            "v1",
            tuple((token, index) for index, token in enumerate(self._vocab)),
            declared_specials,
        )
        self._bpe_snapshot = self._capture_bpe()
        self._digest = self._identity_digest(self._bpe_snapshot)

    def _capture_bpe(self) -> Mapping[str, Any] | None:
        bpe = getattr(self.model, "bpe", None)
        if bpe is None:
            return None
        snapshot = getattr(bpe, "snapshot", None)
        if not callable(snapshot):
            raise TokenizerContractError("attached BPE must support snapshot")
        value = snapshot()
        if not isinstance(value, Mapping):
            raise TokenizerContractError("invalid BPE snapshot")
        canonical_bytes(value)
        return dict(value)

    def _identity_digest(self, bpe: Mapping[str, Any] | None) -> str:
        return digest_json(
            {
                "schema": self.SCHEMA,
                "vocabulary_manifest_digest": self._manifest.digest,
                "bpe": bpe,
                "normalization": "model-native-exact-source-digest-v1",
            }
        )

    @property
    def digest(self) -> str:
        return self._digest

    @property
    def vocab_size(self) -> int:
        return len(self._vocab)

    @property
    def vocabulary_manifest(self) -> VocabularyManifest:
        return self._manifest

    def special_token_id(self, name: str, *, required: bool = False) -> int | None:
        if not isinstance(name, str) or not name:
            raise TokenizerContractError("special token name required")
        token_id = self._manifest.special_tokens.get(name)
        if token_id is None and required:
            raise TokenizerContractError(f"tokenizer does not declare {name} token")
        return token_id

    def assert_unchanged(self) -> None:
        current_vocab = tuple(str(token) for token in self.model.itos)
        if current_vocab != self._vocab or int(self.model.unk) != self._manifest.special_tokens["unk"]:
            raise TokenizerContractError("model vocabulary changed after admission")
        for name in ("pad", "bos", "eos"):
            admitted = self._manifest.special_tokens.get(name)
            current = getattr(self.model, name, None)
            if admitted is None:
                if current is not None:
                    raise TokenizerContractError("model special-token policy changed after admission")
            elif current != admitted:
                raise TokenizerContractError("model special-token policy changed after admission")
        if self._identity_digest(self._capture_bpe()) != self._digest:
            raise TokenizerContractError("BPE/tokenizer state changed after admission")

    def encode_ids(self, text: str) -> tuple[int, ...]:
        if not isinstance(text, str):
            raise TokenizerContractError("text must be a string")
        if len(text) > self.limits.max_chars:
            raise TokenizerContractError("text character budget exceeded")
        try:
            text.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise TokenizerContractError("text is not UTF-8 encodable Unicode") from exc
        try:
            raw_ids = self.model._ids(text)
        except Exception as exc:
            raise TokenizerContractError("native tokenizer encode failed") from exc
        if not isinstance(raw_ids, (list, tuple)):
            raise TokenizerContractError("native tokenizer emitted invalid token container")
        ids_list: list[int] = []
        for value in raw_ids:
            if not _is_int(value):
                raise TokenizerContractError("native tokenizer emitted non-integer token id")
            ids_list.append(int(value))
        ids = tuple(ids_list)
        if not ids:
            ids = (self.model.unk,)
        if len(ids) > self.limits.max_tokens:
            raise TokenizerContractError("token budget exceeded")
        if any(token_id < 0 or token_id >= self.vocab_size for token_id in ids):
            raise TokenizerContractError("model emitted token outside vocabulary")
        return ids

    def encode_sequence(self, text: str) -> TokenSequence:
        return TokenSequence(
            self.digest,
            self.encode_ids(text),
            sha256(text.encode("utf-8")).hexdigest(),
        )

    def token_text(self, token_id: int) -> str:
        if not _is_int(token_id) or not 0 <= token_id < self.vocab_size:
            raise TokenizerContractError("token id outside vocabulary")
        return self._vocab[token_id]

    def decode_ids(self, token_ids: Sequence[int]) -> str:
        ids = tuple(token_ids)
        if len(ids) > self.limits.max_tokens:
            raise TokenizerContractError("decode token budget exceeded")
        pieces = tuple(self.token_text(token_id) for token_id in ids)
        if not pieces:
            return ""
        bpe = getattr(self.model, "bpe", None)
        bpe_vocab = getattr(bpe, "stoi", None)
        decode = getattr(bpe, "decode", None)
        if isinstance(bpe_vocab, Mapping) and callable(decode):
            if all(piece != UNK and piece in bpe_vocab for piece in pieces):
                try:
                    value = decode(pieces)
                except Exception as exc:
                    raise TokenizerContractError("BPE decode failed") from exc
                if not isinstance(value, str):
                    raise TokenizerContractError("BPE decode emitted non-string value")
                try:
                    value.encode("utf-8", errors="strict")
                except UnicodeEncodeError as exc:
                    raise TokenizerContractError("BPE decode emitted invalid Unicode") from exc
                return value
        return " ".join(pieces)

    def checkpoint(self) -> Mapping[str, Any]:
        return {
            "schema": self.SCHEMA,
            "vocabulary_manifest_digest": self._manifest.digest,
            "vocabulary": list(self._vocab),
            "unknown_token_id": int(self.model.unk),
            "bpe": self._bpe_snapshot,
            "digest": self.digest,
        }

    def assert_checkpoint_matches(self, checkpoint: Mapping[str, Any]) -> None:
        if checkpoint.get("schema") != self.SCHEMA:
            raise TokenizerContractError("unsupported tokenizer checkpoint")
        if checkpoint.get("digest") != self.digest:
            raise TokenizerContractError("tokenizer checkpoint digest mismatch")
        if tuple(checkpoint.get("vocabulary") or ()) != self._vocab:
            raise TokenizerContractError("tokenizer checkpoint vocabulary mismatch")
        if checkpoint.get("vocabulary_manifest_digest") != self._manifest.digest:
            raise TokenizerContractError("tokenizer manifest mismatch")


class StreamingTextFeed:
    """Bounded chunk ingestion with chunk-boundary-independent tokenization."""

    def __init__(self, *, limits: TokenizerLimits | None = None) -> None:
        self.limits = limits or TokenizerLimits()
        self._chunks: list[str] = []
        self._chars = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def push(self, chunk: str) -> None:
        if self._closed:
            raise TokenizerContractError("text feed already finalized")
        if not isinstance(chunk, str):
            raise TokenizerContractError("text chunk must be a string")
        if len(chunk) > self.limits.max_chunk_chars:
            raise TokenizerContractError("text chunk budget exceeded")
        if len(self._chunks) >= self.limits.max_chunks:
            raise TokenizerContractError("text chunk count budget exceeded")
        if self._chars + len(chunk) > self.limits.max_chars:
            raise TokenizerContractError("text feed character budget exceeded")
        try:
            chunk.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise TokenizerContractError("text chunk is not UTF-8 encodable Unicode") from exc
        self._chunks.append(chunk)
        self._chars += len(chunk)

    def consume_text(self) -> str:
        """Consume validated chunks once; no tokenization before normalization."""
        if self._closed:
            raise TokenizerContractError("text feed already finalized")
        self._closed = True
        chunks = self._chunks
        self._chunks = []
        return "".join(chunks)

    def finalize(self, tokenizer: NativeTokenizer) -> TokenSequence:
        if self._closed:
            raise TokenizerContractError("text feed already finalized")
        if not isinstance(tokenizer, NativeTokenizer):
            raise TokenizerContractError("NativeTokenizer required")
        self._closed = True
        return tokenizer.encode_sequence("".join(self._chunks))


def iter_context_windows(
    sequence: TokenSequence,
    *,
    context_size: int,
    stride: int | None = None,
    include_tail: bool = True,
) -> Iterator[TokenWindow]:
    if not isinstance(sequence, TokenSequence):
        raise TokenizerContractError("TokenSequence required")
    size = _positive(context_size, "context_size", MAX_TOKENS)
    step = size if stride is None else _positive(stride, "stride", MAX_TOKENS)
    if step > size:
        raise TokenizerContractError("stride cannot exceed context size")
    start = 0
    while start < len(sequence.token_ids):
        stop = min(len(sequence.token_ids), start + size)
        if stop - start < size and not include_tail:
            break
        yield TokenWindow(start, stop, tuple(sequence.token_ids[start:stop]), sequence.digest)
        if stop == len(sequence.token_ids):
            break
        start += step


def batch_token_windows(
    windows: Iterable[TokenWindow],
    *,
    max_batch_size: int,
    max_tokens_per_batch: int,
) -> tuple[TokenBatch, ...]:
    batch_size = _positive(max_batch_size, "max_batch_size", 4096)
    token_budget = _positive(max_tokens_per_batch, "max_tokens_per_batch", MAX_TOKENS)
    batches: list[TokenBatch] = []
    current: list[TokenWindow] = []
    current_tokens = 0
    for window in windows:
        if not isinstance(window, TokenWindow):
            raise TokenizerContractError("TokenWindow required")
        demand = len(window.token_ids)
        if demand > token_budget:
            raise TokenizerContractError("token window exceeds batch token budget")
        if current and (len(current) >= batch_size or current_tokens + demand > token_budget):
            batches.append(TokenBatch(tuple(current), current_tokens))
            current = []
            current_tokens = 0
        current.append(window)
        current_tokens += demand
    if current:
        batches.append(TokenBatch(tuple(current), current_tokens))
    return tuple(batches)


def serialize_token_sequence(sequence: TokenSequence) -> bytes:
    payload = canonical_bytes(
        {
            "tokenizer_digest": sequence.tokenizer_digest,
            "token_ids": list(sequence.token_ids),
            "source_text_digest": sequence.source_text_digest,
        }
    )
    if len(payload) > MAX_SERIALIZED_SEQUENCE_BYTES:
        raise TokenizerContractError("serialized token sequence exceeds byte budget")
    return payload


def deserialize_token_sequence(payload: bytes) -> TokenSequence:
    if not isinstance(payload, bytes) or len(payload) > MAX_SERIALIZED_SEQUENCE_BYTES:
        raise TokenizerContractError("invalid serialized token sequence bytes")
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise TokenizerContractError("duplicate serialized JSON key")
            result[key] = item
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenizerContractError("invalid serialized token sequence") from exc
    if not isinstance(value, dict) or set(value) != {
        "tokenizer_digest",
        "token_ids",
        "source_text_digest",
    }:
        raise TokenizerContractError("serialized token sequence has invalid shape")
    token_ids = value["token_ids"]
    if not isinstance(token_ids, list):
        raise TokenizerContractError("serialized token_ids must be a list")
    if len(token_ids) > MAX_TOKENS:
        raise TokenizerContractError("serialized token sequence exceeds token budget")
    if any(not _is_int(token_id) or token_id < 0 or token_id >= 2**31 for token_id in token_ids):
        raise TokenizerContractError("serialized token_ids contain invalid id")
    for name in ("tokenizer_digest", "source_text_digest"):
        digest = value[name]
        if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise TokenizerContractError(f"serialized {name} is invalid")
    return TokenSequence(
        value["tokenizer_digest"],
        tuple(token_ids),
        value["source_text_digest"],
    )


__all__ = [
    "ModelRuntimeError",
    "NativeTokenizer",
    "StreamingTextFeed",
    "TokenBatch",
    "TokenSequence",
    "TokenWindow",
    "TokenizerContractError",
    "TokenizerLimits",
    "VocabularyManifest",
    "batch_token_windows",
    "deserialize_token_sequence",
    "iter_context_windows",
    "serialize_token_sequence",
]
