"""Deterministic model-bound tokenization for the native LLM runtime.

This module turns the FLGB-02 tokenization contract into an executable bridge.
It deliberately does not own provider credentials or network access. A
NativeTokenizer is bound to one concrete model vocabulary and, when present,
that model's BPE merge table so token identity cannot silently drift between
ingestion, inference, replay, and checkpoint restore.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence

from .flgb_model_runtime import (
    MAX_TOKENS,
    ModelRuntimeError,
    TokenSequence,
    VocabularyManifest,
)

TOKENIZER_SCHEMA = "skeleton.ai.model-tokenizer.v1"


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelRuntimeError("tokenizer state is not canonical-json encodable") from exc


def _digest(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _text_digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TokenizerState:
    """Serializable identity of the exact text-to-token transform."""

    schema: str
    vocabulary: tuple[str, ...]
    bpe: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        if self.schema != TOKENIZER_SCHEMA:
            raise ModelRuntimeError("unsupported tokenizer schema")
        if not self.vocabulary or len(self.vocabulary) > MAX_TOKENS:
            raise ModelRuntimeError("tokenizer vocabulary size out of bounds")
        if len(set(self.vocabulary)) != len(self.vocabulary):
            raise ModelRuntimeError("tokenizer vocabulary contains duplicates")
        if any(not isinstance(token, str) for token in self.vocabulary):
            raise ModelRuntimeError("tokenizer vocabulary tokens must be strings")
        if self.bpe is not None and not isinstance(self.bpe, Mapping):
            raise ModelRuntimeError("tokenizer BPE state must be a mapping")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "vocabulary": list(self.vocabulary),
            "bpe": None if self.bpe is None else dict(self.bpe),
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


class NativeTokenizer:
    """Strict adapter from text to the token IDs consumed by TinyTransformer."""

    def __init__(self, model: Any) -> None:
        if model is None or not hasattr(model, "itos") or not hasattr(model, "stoi"):
            raise ModelRuntimeError("model with vocabulary required")
        vocabulary = tuple(str(token) for token in model.itos)
        bpe = getattr(model, "bpe", None)
        bpe_state: Mapping[str, Any] | None = None
        if bpe is not None:
            if not hasattr(bpe, "snapshot"):
                raise ModelRuntimeError("model BPE is not serializable")
            raw = bpe.snapshot()
            if not isinstance(raw, Mapping):
                raise ModelRuntimeError("model BPE snapshot must be a mapping")
            bpe_state = dict(raw)
        self._model = model
        self._state = TokenizerState(TOKENIZER_SCHEMA, vocabulary, bpe_state)

    @property
    def state(self) -> TokenizerState:
        return self._state

    @property
    def digest(self) -> str:
        return self._state.digest

    @property
    def vocabulary_size(self) -> int:
        return len(self._state.vocabulary)

    def manifest(self) -> VocabularyManifest:
        specials = {"unk": int(getattr(self._model, "unk", 0))}
        return VocabularyManifest(
            "native-model-tokenizer",
            self.digest[:16],
            tuple((token, index) for index, token in enumerate(self._state.vocabulary)),
            specials,
        )

    def encode_ids(self, text: str) -> tuple[int, ...]:
        if not isinstance(text, str):
            raise ModelRuntimeError("text must be a string")
        try:
            raw = self._model._ids(text)
        except Exception as exc:
            raise ModelRuntimeError("model tokenizer failed") from exc
        ids = tuple(raw)
        if not ids:
            ids = (getattr(self._model, "unk", 0),)
        if len(ids) > MAX_TOKENS:
            raise ModelRuntimeError("token sequence exceeds budget")
        upper = self.vocabulary_size
        if any(
            isinstance(token_id, bool)
            or not isinstance(token_id, int)
            or token_id < 0
            or token_id >= upper
            for token_id in ids
        ):
            raise ModelRuntimeError("tokenizer emitted invalid token id")
        return ids

    def encode(self, text: str) -> TokenSequence:
        return TokenSequence(self.digest, self.encode_ids(text), _text_digest(text))

    def decode_ids(self, token_ids: Sequence[int]) -> str:
        ids = tuple(token_ids)
        if len(ids) > MAX_TOKENS:
            raise ModelRuntimeError("token sequence exceeds budget")
        pieces: list[str] = []
        for token_id in ids:
            if isinstance(token_id, bool) or not isinstance(token_id, int):
                raise ModelRuntimeError("token ids must be integers")
            if token_id < 0 or token_id >= self.vocabulary_size:
                raise ModelRuntimeError("unknown token id")
            pieces.append(self._state.vocabulary[token_id])
        bpe = getattr(self._model, "bpe", None)
        if bpe is not None and hasattr(bpe, "decode"):
            # A model may carry a BPE helper while still using a word-level
            # vocabulary fallback. Only decode as BPE when the learned BPE
            # alphabet/merges are actually represented by the model vocab.
            bpe_vocab = tuple(str(piece) for piece in getattr(bpe, "itos", ()) if str(piece) != "�")
            if bpe_vocab and all(piece in self._model.stoi for piece in bpe_vocab):
                try:
                    return str(bpe.decode(pieces))
                except Exception as exc:
                    raise ModelRuntimeError("model BPE decode failed") from exc
        return " ".join(piece for piece in pieces if piece != "__unk__")

    def encode_many(self, texts: Iterable[str]) -> tuple[TokenSequence, ...]:
        out: list[TokenSequence] = []
        for text in texts:
            if len(out) >= MAX_TOKENS:
                raise ModelRuntimeError("tokenizer batch exceeds hard item budget")
            out.append(self.encode(text))
        return tuple(out)


__all__ = [
    "ModelRuntimeError",
    "NativeTokenizer",
    "TOKENIZER_SCHEMA",
    "TokenSequence",
    "TokenizerState",
    "VocabularyManifest",
]
