"""Bounded NumPy recurrent language model for credential-free local inference.

This is a compact Elman-style recurrent LM intended as a real learned local
backend, not as a state-of-the-art quality claim.  It gives the canonical local
provider a trainable sequence model whose weights are fully materialized inside
one content-addressed JSON artifact.

The model deliberately owns no tools, policy, networking, or persistence.
Those authorities stay in the existing cognitive runtime.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import threading
import time
from typing import Any, Mapping, Sequence

import numpy as np

from .local import (
    LocalInferenceCancelled,
    LocalInferenceRequest,
    LocalInferenceResult,
    _EOS,
    _detokenize,
    _tokenize,
)


_SCHEMA = "skeleton.numpy_recurrent_lm.v1"
_TOKENIZER = "skeleton.regex_tokenizer.v1"
_UNK = "<|unk|>"
_MAX_VOCAB = 65_536
_MAX_HIDDEN = 4_096
_MAX_SEQUENCE_TOKENS = 8_192
_MAX_PARAMETER_BYTES = 96 * 1024 * 1024
_MAX_TRAINING_DOCUMENTS = 4_096
_MAX_TRAINING_TOKENS = 2_000_000
_MAX_TRAINING_WORK = 2_000_000_000
_MAX_INFERENCE_WORK = 300_000_000


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        _stable_json(value).encode("utf-8")
    ).hexdigest()


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(
            f"{field} must be in [{minimum}, {maximum}]"
        )
    return value


def _require_float(
    value: object,
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} must be finite")
    if numeric < minimum or numeric > maximum:
        raise ValueError(
            f"{field} must be in [{minimum}, {maximum}]"
        )
    return numeric


def _parameter_bytes(vocab_size: int, hidden_size: int) -> int:
    floats = (
        (vocab_size * hidden_size)
        + (hidden_size * hidden_size)
        + hidden_size
        + (hidden_size * vocab_size)
        + vocab_size
    )
    return floats * 4


def _matrix(
    value: object,
    field: str,
    *,
    rows: int,
    columns: int,
) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not a numeric matrix") from exc
    if array.shape != (rows, columns):
        raise ValueError(
            f"{field} must have shape {(rows, columns)}, got {array.shape}"
        )
    if not np.isfinite(array).all():
        raise ValueError(f"{field} contains non-finite values")
    return np.ascontiguousarray(array, dtype=np.float32)


def _vector(
    value: object,
    field: str,
    *,
    length: int,
) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not a numeric vector") from exc
    if array.shape != (length,):
        raise ValueError(
            f"{field} must have shape {(length,)}, got {array.shape}"
        )
    if not np.isfinite(array).all():
        raise ValueError(f"{field} contains non-finite values")
    return np.ascontiguousarray(array, dtype=np.float32)


class NumpyRecurrentLM:
    """Small trainable recurrent language model implementing LocalModelBackend."""

    schema_version = _SCHEMA

    def __init__(
        self,
        *,
        model_id: str,
        vocab: Sequence[str],
        hidden_size: int,
        embedding: object,
        recurrent: object,
        recurrent_bias: object,
        output: object,
        output_bias: object,
        temperature: float = 0.8,
    ) -> None:
        normalized_id = str(model_id).strip()
        if not normalized_id or len(normalized_id) > 256:
            raise ValueError("model_id is invalid")
        hidden = _require_int(
            hidden_size,
            "hidden_size",
            minimum=4,
            maximum=_MAX_HIDDEN,
        )
        normalized_vocab = tuple(str(token) for token in vocab)
        if (
            len(normalized_vocab) < 3
            or len(normalized_vocab) > _MAX_VOCAB
            or len(set(normalized_vocab)) != len(normalized_vocab)
            or any(not token for token in normalized_vocab)
        ):
            raise ValueError("vocab is invalid")
        if normalized_vocab[0] != _UNK or normalized_vocab[1] != _EOS:
            raise ValueError(
                "vocab must reserve <|unk|> and <|eos|> as first tokens"
            )

        vocab_size = len(normalized_vocab)
        if _parameter_bytes(vocab_size, hidden) > _MAX_PARAMETER_BYTES:
            raise ValueError(
                "recurrent model parameter memory exceeds hard bound"
            )
        self.model_id = normalized_id
        self.hidden_size = hidden
        self.vocab = normalized_vocab
        self.temperature = _require_float(
            temperature,
            "temperature",
            minimum=0.05,
            maximum=5.0,
        )
        self.embedding = _matrix(
            embedding,
            "embedding",
            rows=vocab_size,
            columns=hidden,
        )
        self.recurrent = _matrix(
            recurrent,
            "recurrent",
            rows=hidden,
            columns=hidden,
        )
        self.recurrent_bias = _vector(
            recurrent_bias,
            "recurrent_bias",
            length=hidden,
        )
        self.output = _matrix(
            output,
            "output",
            rows=hidden,
            columns=vocab_size,
        )
        self.output_bias = _vector(
            output_bias,
            "output_bias",
            length=vocab_size,
        )
        self._token_to_id = {
            token: index
            for index, token in enumerate(self.vocab)
        }
        self._model_digest = _digest(
            self.to_dict(include_digest=False)
        )

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": _SCHEMA,
            "tokenizer": _TOKENIZER,
            "model_id": self.model_id,
            "dtype": "float32",
            "hidden_size": self.hidden_size,
            "temperature": self.temperature,
            "vocab": list(self.vocab),
            "embedding": self.embedding.tolist(),
            "recurrent": self.recurrent.tolist(),
            "recurrent_bias": self.recurrent_bias.tolist(),
            "output": self.output.tolist(),
            "output_bias": self.output_bias.tolist(),
        }
        if include_digest:
            payload["model_digest"] = self.model_digest
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "NumpyRecurrentLM":
        if not isinstance(payload, Mapping):
            raise TypeError("recurrent model payload must be a mapping")
        if payload.get("schema_version") != _SCHEMA:
            raise ValueError(
                "unsupported NumPy recurrent model schema"
            )
        if payload.get("tokenizer") not in {None, _TOKENIZER}:
            raise ValueError("unsupported recurrent model tokenizer")
        if payload.get("dtype") not in {None, "float32"}:
            raise ValueError("unsupported recurrent model dtype")
        vocab = payload.get("vocab")
        if not isinstance(vocab, list):
            raise ValueError("recurrent model vocab must be a list")
        model = cls(
            model_id=str(payload.get("model_id") or ""),
            vocab=tuple(str(item) for item in vocab),
            hidden_size=_require_int(
                payload.get("hidden_size"),
                "hidden_size",
                minimum=4,
                maximum=_MAX_HIDDEN,
            ),
            embedding=payload.get("embedding"),
            recurrent=payload.get("recurrent"),
            recurrent_bias=payload.get("recurrent_bias"),
            output=payload.get("output"),
            output_bias=payload.get("output_bias"),
            temperature=_require_float(
                payload.get("temperature", 0.8),
                "temperature",
                minimum=0.05,
                maximum=5.0,
            ),
        )
        claimed = payload.get("model_digest")
        if claimed is not None:
            if not isinstance(claimed, str) or claimed != model.model_digest:
                raise ValueError(
                    "NumPy recurrent model digest mismatch"
                )
        return model

    @classmethod
    def train(
        cls,
        corpus: Sequence[str],
        *,
        model_id: str = "skeleton-numpy-rnn-v1",
        hidden_size: int = 32,
        epochs: int = 4,
        learning_rate: float = 0.05,
        max_vocab: int = 4_096,
        max_document_tokens: int = 1_024,
        seed: int = 0,
        temperature: float = 0.8,
    ) -> "NumpyRecurrentLM":
        """Train a bounded Elman RNN with deterministic truncated BPTT."""

        if not corpus:
            raise ValueError("training corpus must be non-empty")
        if len(corpus) > _MAX_TRAINING_DOCUMENTS:
            raise ValueError(
                "training corpus document count exceeds hard bound"
            )
        hidden = _require_int(
            hidden_size,
            "hidden_size",
            minimum=4,
            maximum=min(_MAX_HIDDEN, 1_024),
        )
        rounds = _require_int(
            epochs,
            "epochs",
            minimum=1,
            maximum=1_000,
        )
        vocab_limit = _require_int(
            max_vocab,
            "max_vocab",
            minimum=3,
            maximum=_MAX_VOCAB,
        )
        document_limit = _require_int(
            max_document_tokens,
            "max_document_tokens",
            minimum=2,
            maximum=_MAX_SEQUENCE_TOKENS,
        )
        rate = _require_float(
            learning_rate,
            "learning_rate",
            minimum=1e-6,
            maximum=1.0,
        )
        temp = _require_float(
            temperature,
            "temperature",
            minimum=0.05,
            maximum=5.0,
        )
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")

        tokenized: list[tuple[str, ...]] = []
        counts: Counter[str] = Counter()
        total_training_tokens = 0
        for index, document in enumerate(corpus):
            if not isinstance(document, str) or not document.strip():
                raise ValueError(
                    f"training document {index} must be non-empty text"
                )
            tokens = tuple(_tokenize(document))[:document_limit]
            if not tokens:
                raise ValueError(
                    f"training document {index} produced no tokens"
                )
            total_training_tokens += len(tokens)
            if total_training_tokens > _MAX_TRAINING_TOKENS:
                raise ValueError(
                    "training corpus token count exceeds hard bound"
                )
            tokenized.append(tokens)
            counts.update(tokens)

        lexical = sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        selected = [
            token
            for token, _count in lexical
            if token not in {_UNK, _EOS}
        ][: max(1, vocab_limit - 2)]
        vocab = (_UNK, _EOS, *selected)
        token_to_id = {
            token: index
            for index, token in enumerate(vocab)
        }
        unk_id = token_to_id[_UNK]
        eos_id = token_to_id[_EOS]
        sequences: list[np.ndarray] = []
        for tokens in tokenized:
            ids = [
                token_to_id.get(token, unk_id)
                for token in tokens
            ]
            ids.append(eos_id)
            if len(ids) >= 2:
                sequences.append(
                    np.asarray(ids, dtype=np.int64)
                )
        if not sequences:
            raise ValueError(
                "training corpus produced no next-token examples"
            )

        vocab_size = len(vocab)
        if _parameter_bytes(vocab_size, hidden) > _MAX_PARAMETER_BYTES:
            raise ValueError(
                "training configuration exceeds parameter memory bound"
            )
        training_steps = sum(
            max(0, len(sequence) - 1)
            for sequence in sequences
        )
        approximate_work = (
            training_steps
            * rounds
            * (
                (hidden * hidden)
                + (hidden * vocab_size)
            )
            * 4
        )
        if approximate_work > _MAX_TRAINING_WORK:
            raise ValueError(
                "training configuration exceeds compute bound"
            )

        rng = np.random.default_rng(seed)
        scale = np.float32(1.0 / math.sqrt(hidden))
        embedding = rng.normal(
            0.0,
            float(scale),
            size=(vocab_size, hidden),
        ).astype(np.float32)
        recurrent = rng.normal(
            0.0,
            float(scale) * 0.5,
            size=(hidden, hidden),
        ).astype(np.float32)
        recurrent_bias = np.zeros(hidden, dtype=np.float32)
        output = rng.normal(
            0.0,
            float(scale),
            size=(hidden, vocab_size),
        ).astype(np.float32)
        output_bias = np.zeros(vocab_size, dtype=np.float32)

        order = np.arange(len(sequences), dtype=np.int64)
        for _epoch in range(rounds):
            rng.shuffle(order)
            for sequence_index in order:
                sequence = sequences[int(sequence_index)]
                inputs = sequence[:-1]
                targets = sequence[1:]
                states: list[np.ndarray] = [
                    np.zeros(hidden, dtype=np.float32)
                ]
                probabilities: list[np.ndarray] = []

                for token_id in inputs:
                    previous = states[-1]
                    hidden_state = np.tanh(
                        embedding[int(token_id)]
                        + previous @ recurrent
                        + recurrent_bias
                    ).astype(np.float32)
                    logits = (
                        hidden_state @ output + output_bias
                    ).astype(np.float64)
                    logits -= float(np.max(logits))
                    exp = np.exp(
                        np.clip(logits, -60.0, 60.0)
                    )
                    probability = (
                        exp / max(float(exp.sum()), 1e-12)
                    ).astype(np.float32)
                    states.append(hidden_state)
                    probabilities.append(probability)

                d_embedding = np.zeros_like(embedding)
                d_recurrent = np.zeros_like(recurrent)
                d_recurrent_bias = np.zeros_like(
                    recurrent_bias
                )
                d_output = np.zeros_like(output)
                d_output_bias = np.zeros_like(output_bias)
                dh_next = np.zeros(hidden, dtype=np.float32)

                for position in range(
                    len(inputs) - 1,
                    -1,
                    -1,
                ):
                    dy = probabilities[position].copy()
                    dy[int(targets[position])] -= np.float32(1.0)
                    state = states[position + 1]
                    previous = states[position]
                    d_output += np.outer(state, dy).astype(
                        np.float32
                    )
                    d_output_bias += dy
                    dh = dy @ output.T + dh_next
                    dtanh = (
                        (np.float32(1.0) - state * state)
                        * dh
                    ).astype(np.float32)
                    d_embedding[int(inputs[position])] += dtanh
                    d_recurrent += np.outer(
                        previous,
                        dtanh,
                    ).astype(np.float32)
                    d_recurrent_bias += dtanh
                    dh_next = (
                        dtanh @ recurrent.T
                    ).astype(np.float32)

                normalizer = np.float32(
                    1.0 / max(1, len(inputs))
                )
                for gradient in (
                    d_embedding,
                    d_recurrent,
                    d_recurrent_bias,
                    d_output,
                    d_output_bias,
                ):
                    gradient *= normalizer
                    np.clip(
                        gradient,
                        -5.0,
                        5.0,
                        out=gradient,
                    )

                embedding -= np.float32(rate) * d_embedding
                recurrent -= np.float32(rate) * d_recurrent
                recurrent_bias -= (
                    np.float32(rate) * d_recurrent_bias
                )
                output -= np.float32(rate) * d_output
                output_bias -= np.float32(rate) * d_output_bias

        return cls(
            model_id=model_id,
            vocab=vocab,
            hidden_size=hidden,
            embedding=embedding,
            recurrent=recurrent,
            recurrent_bias=recurrent_bias,
            output=output,
            output_bias=output_bias,
            temperature=temp,
        )

    def _token_id(self, token: str) -> int:
        return self._token_to_id.get(token, 0)

    def _advance(
        self,
        hidden: np.ndarray,
        token_id: int,
    ) -> np.ndarray:
        return np.tanh(
            self.embedding[token_id]
            + hidden @ self.recurrent
            + self.recurrent_bias
        ).astype(np.float32)

    def _sample(
        self,
        hidden: np.ndarray,
        rng: np.random.Generator,
    ) -> int:
        logits = (
            hidden @ self.output + self.output_bias
        ).astype(np.float64)
        logits /= self.temperature
        logits -= float(np.max(logits))
        exp = np.exp(np.clip(logits, -60.0, 60.0))
        probabilities = exp / max(float(exp.sum()), 1e-12)
        return int(
            rng.choice(
                self.vocab_size,
                p=probabilities,
            )
        )

    def infer(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError(
                "request must be LocalInferenceRequest"
            )
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")

        started = time.perf_counter()
        context_step_cost = max(
            1,
            self.hidden_size * self.hidden_size,
        )
        generation_step_cost = max(
            1,
            context_step_cost
            + (self.hidden_size * self.vocab_size),
        )
        generation_limit = min(
            request.max_output_tokens,
            max(
                1,
                (_MAX_INFERENCE_WORK // 2)
                // generation_step_cost,
            ),
        )
        remaining_work = max(
            1,
            _MAX_INFERENCE_WORK
            - (generation_limit * generation_step_cost),
        )
        context_limit = min(
            _MAX_SEQUENCE_TOKENS,
            max(1, remaining_work // context_step_cost),
        )
        input_tokens = list(
            _tokenize(request.rendered_input)
        )[-context_limit:]
        hidden = np.zeros(
            self.hidden_size,
            dtype=np.float32,
        )
        for token in input_tokens:
            if cancel.is_set():
                raise LocalInferenceCancelled(
                    "local recurrent inference cancelled"
                )
            hidden = self._advance(
                hidden,
                self._token_id(token),
            )

        seed = (
            int(request.seed)
            ^ int(self.model_digest[:16], 16)
        ) & ((1 << 63) - 1)
        rng = np.random.default_rng(seed)
        generated: list[str] = []
        finish_reason = "length"

        for _ in range(generation_limit):
            if cancel.is_set():
                raise LocalInferenceCancelled(
                    "local recurrent inference cancelled"
                )
            token_id = self._sample(hidden, rng)
            token = self.vocab[token_id]
            if token == _EOS:
                finish_reason = "completed"
                break
            if token == _UNK:
                ranked = np.argsort(
                    hidden @ self.output + self.output_bias
                )[::-1]
                replacement = next(
                    (
                        self.vocab[int(index)]
                        for index in ranked
                        if self.vocab[int(index)]
                        not in {_EOS, _UNK}
                    ),
                    None,
                )
                if replacement is None:
                    finish_reason = "completed"
                    break
                token = replacement
                token_id = self._token_id(token)

            generated.append(token)
            hidden = self._advance(hidden, token_id)
            rendered = _detokenize(generated)
            if any(
                rendered.endswith(marker)
                for marker in request.stop
            ):
                finish_reason = "completed"
                break

        if (
            finish_reason == "length"
            and generation_limit < request.max_output_tokens
        ):
            finish_reason = "length"

        text = _detokenize(generated)
        if not text:
            text = (
                "I do not have enough learned local context "
                "to answer."
            )
        response_id = "local-rnn:" + _digest(
            {
                "model": self.model_digest,
                "request": request.digest,
                "text": text,
            }
        )[:32]
        return LocalInferenceResult(
            text=text,
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=len(input_tokens),
            output_tokens=len(generated),
            finish_reason=finish_reason,
            response_id=response_id,
            latency_ms=(
                time.perf_counter() - started
            )
            * 1000.0,
        )


__all__ = ["NumpyRecurrentLM"]
