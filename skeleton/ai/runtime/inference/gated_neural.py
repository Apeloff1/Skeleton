"""Bounded NumPy gated recurrent language model for local inference.

This is a compact GRU-style recurrent LM.  It keeps the same provider-neutral
local inference contract as the legacy Elman backend while using update/reset
gates to preserve useful state over longer contexts and improve gradient flow.

The implementation is intentionally dependency-light: NumPy only, no network,
no tools, and one content-addressed JSON artifact.
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


_SCHEMA = "skeleton.numpy_gated_recurrent_lm.v1"
_TOKENIZER = "skeleton.regex_tokenizer.v1"
_UNK = "<|unk|>"
_MAX_VOCAB = 65_536
_MAX_HIDDEN = 2_048
_MAX_SEQUENCE_TOKENS = 8_192
_MAX_PARAMETER_BYTES = 128 * 1024 * 1024
_MAX_TRAINING_DOCUMENTS = 4_096
_MAX_TRAINING_TOKENS = 2_000_000
_MAX_TRAINING_WORK = 3_000_000_000
_MAX_INFERENCE_WORK = 400_000_000


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
    if not minimum <= value <= maximum:
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
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(
            f"{field} must be finite and in [{minimum}, {maximum}]"
        )
    return result


def _parameter_bytes(vocab_size: int, hidden_size: int) -> int:
    floats = (
        (vocab_size * hidden_size)
        + (3 * hidden_size * hidden_size)
        + (3 * hidden_size)
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


def _sigmoid(value: np.ndarray) -> np.ndarray:
    clipped = np.clip(value, -30.0, 30.0)
    return (
        np.float32(1.0)
        / (np.float32(1.0) + np.exp(-clipped))
    ).astype(np.float32)


class NumpyGatedRecurrentLM:
    """Trainable GRU-style local language model."""

    schema_version = _SCHEMA

    def __init__(
        self,
        *,
        model_id: str,
        vocab: Sequence[str],
        hidden_size: int,
        embedding: object,
        update_recurrent: object,
        update_bias: object,
        reset_recurrent: object,
        reset_bias: object,
        candidate_recurrent: object,
        candidate_bias: object,
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
                "gated recurrent model parameter memory exceeds hard bound"
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
        self.update_recurrent = _matrix(
            update_recurrent,
            "update_recurrent",
            rows=hidden,
            columns=hidden,
        )
        self.update_bias = _vector(
            update_bias,
            "update_bias",
            length=hidden,
        )
        self.reset_recurrent = _matrix(
            reset_recurrent,
            "reset_recurrent",
            rows=hidden,
            columns=hidden,
        )
        self.reset_bias = _vector(
            reset_bias,
            "reset_bias",
            length=hidden,
        )
        self.candidate_recurrent = _matrix(
            candidate_recurrent,
            "candidate_recurrent",
            rows=hidden,
            columns=hidden,
        )
        self.candidate_bias = _vector(
            candidate_bias,
            "candidate_bias",
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
            "architecture": "gru_style",
            "hidden_size": self.hidden_size,
            "temperature": self.temperature,
            "vocab": list(self.vocab),
            "embedding": self.embedding.tolist(),
            "update_recurrent": self.update_recurrent.tolist(),
            "update_bias": self.update_bias.tolist(),
            "reset_recurrent": self.reset_recurrent.tolist(),
            "reset_bias": self.reset_bias.tolist(),
            "candidate_recurrent": self.candidate_recurrent.tolist(),
            "candidate_bias": self.candidate_bias.tolist(),
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
    ) -> "NumpyGatedRecurrentLM":
        if not isinstance(payload, Mapping):
            raise TypeError("gated recurrent payload must be a mapping")
        if payload.get("schema_version") != _SCHEMA:
            raise ValueError(
                "unsupported NumPy gated recurrent model schema"
            )
        if payload.get("tokenizer") not in {None, _TOKENIZER}:
            raise ValueError("unsupported gated recurrent tokenizer")
        if payload.get("dtype") not in {None, "float32"}:
            raise ValueError("unsupported gated recurrent dtype")
        if payload.get("architecture") not in {None, "gru_style"}:
            raise ValueError("unsupported gated recurrent architecture")
        vocab = payload.get("vocab")
        if not isinstance(vocab, list):
            raise ValueError("gated recurrent vocab must be a list")
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
            update_recurrent=payload.get("update_recurrent"),
            update_bias=payload.get("update_bias"),
            reset_recurrent=payload.get("reset_recurrent"),
            reset_bias=payload.get("reset_bias"),
            candidate_recurrent=payload.get("candidate_recurrent"),
            candidate_bias=payload.get("candidate_bias"),
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
        if claimed is not None and claimed != model.model_digest:
            raise ValueError(
                "NumPy gated recurrent model digest mismatch"
            )
        return model

    @classmethod
    def train(
        cls,
        corpus: Sequence[str],
        *,
        model_id: str = "skeleton-numpy-gru-v1",
        hidden_size: int = 32,
        epochs: int = 4,
        learning_rate: float = 0.03,
        max_vocab: int = 4_096,
        max_document_tokens: int = 1_024,
        seed: int = 0,
        temperature: float = 0.8,
        early_stopping_patience: int = 0,
        min_relative_improvement: float = 0.0,
        shuffle_each_epoch: bool = True,
        gradient_accumulation_steps: int = 1,
    ) -> "NumpyGatedRecurrentLM":
        """Train a bounded GRU-style model with deterministic BPTT."""

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
            maximum=min(_MAX_HIDDEN, 768),
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
        if (
            isinstance(early_stopping_patience, bool)
            or not isinstance(early_stopping_patience, int)
            or not 0 <= early_stopping_patience <= 100
        ):
            raise ValueError(
                "early_stopping_patience must be in [0, 100]"
            )
        min_improvement = _require_float(
            min_relative_improvement,
            "min_relative_improvement",
            minimum=0.0,
            maximum=1.0,
        )
        if not isinstance(shuffle_each_epoch, bool):
            raise TypeError("shuffle_each_epoch must be boolean")
        accumulation_steps = _require_int(
            gradient_accumulation_steps,
            "gradient_accumulation_steps",
            minimum=1,
            maximum=64,
        )

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
                (3 * hidden * hidden)
                + (hidden * vocab_size)
            )
            * 6
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
        update_recurrent = rng.normal(
            0.0,
            float(scale) * 0.35,
            size=(hidden, hidden),
        ).astype(np.float32)
        reset_recurrent = rng.normal(
            0.0,
            float(scale) * 0.35,
            size=(hidden, hidden),
        ).astype(np.float32)
        candidate_recurrent = rng.normal(
            0.0,
            float(scale) * 0.5,
            size=(hidden, hidden),
        ).astype(np.float32)
        update_bias = np.ones(hidden, dtype=np.float32)
        reset_bias = np.zeros(hidden, dtype=np.float32)
        candidate_bias = np.zeros(hidden, dtype=np.float32)
        output = rng.normal(
            0.0,
            float(scale),
            size=(hidden, vocab_size),
        ).astype(np.float32)
        output_bias = np.zeros(vocab_size, dtype=np.float32)

        parameters = (
            update_recurrent,
            update_bias,
            reset_recurrent,
            reset_bias,
            candidate_recurrent,
            candidate_bias,
            output,
            output_bias,
        )
        gradients = tuple(np.zeros_like(item) for item in parameters)
        accumulated = tuple(np.zeros_like(item) for item in parameters)
        acc_embedding_rows: dict[int, np.ndarray] = {}
        accumulated_sequences = 0
        optimizer_steps = 0
        order = np.arange(len(sequences), dtype=np.int64)

        def flush() -> None:
            nonlocal accumulated_sequences, optimizer_steps
            if accumulated_sequences == 0:
                return
            step = np.float32(rate)
            for parameter, gradient in zip(
                parameters,
                accumulated,
                strict=True,
            ):
                parameter[:] -= step * gradient
                gradient.fill(0.0)
            for token_index, gradient in acc_embedding_rows.items():
                embedding[token_index] -= step * gradient
            acc_embedding_rows.clear()
            accumulated_sequences = 0
            optimizer_steps += 1

        loss_history: list[float] = []
        best_loss = math.inf
        stale_epochs = 0
        epochs_completed = 0
        stopped_early = False

        for _epoch in range(rounds):
            if shuffle_each_epoch:
                rng.shuffle(order)
            epoch_loss = 0.0
            epoch_targets = 0

            for sequence_index in order:
                sequence = sequences[int(sequence_index)]
                inputs = sequence[:-1]
                targets = sequence[1:]
                states: list[np.ndarray] = [
                    np.zeros(hidden, dtype=np.float32)
                ]
                updates: list[np.ndarray] = []
                resets: list[np.ndarray] = []
                candidates: list[np.ndarray] = []
                probabilities: list[np.ndarray] = []

                for position, token_id in enumerate(inputs):
                    previous = states[-1]
                    x = embedding[int(token_id)]
                    update_gate = _sigmoid(
                        x
                        + previous @ update_recurrent
                        + update_bias
                    )
                    reset_gate = _sigmoid(
                        x
                        + previous @ reset_recurrent
                        + reset_bias
                    )
                    candidate_state = np.tanh(
                        x
                        + (reset_gate * previous)
                        @ candidate_recurrent
                        + candidate_bias
                    ).astype(np.float32)
                    hidden_state = (
                        (np.float32(1.0) - update_gate)
                        * candidate_state
                        + update_gate * previous
                    ).astype(np.float32)
                    logits = (
                        hidden_state @ output + output_bias
                    ).astype(np.float64)
                    logits -= float(np.max(logits))
                    exp = np.exp(np.clip(logits, -60.0, 60.0))
                    probability = (
                        exp / max(float(exp.sum()), 1e-12)
                    ).astype(np.float32)
                    target_probability = max(
                        float(probability[int(targets[position])]),
                        1e-12,
                    )
                    epoch_loss -= math.log(target_probability)
                    epoch_targets += 1
                    states.append(hidden_state)
                    updates.append(update_gate)
                    resets.append(reset_gate)
                    candidates.append(candidate_state)
                    probabilities.append(probability)

                for gradient in gradients:
                    gradient.fill(0.0)
                d_embedding_rows: dict[int, np.ndarray] = {}
                dh_next = np.zeros(hidden, dtype=np.float32)
                (
                    d_update,
                    d_update_bias,
                    d_reset,
                    d_reset_bias,
                    d_candidate,
                    d_candidate_bias,
                    d_output,
                    d_output_bias,
                ) = gradients

                for position in range(len(inputs) - 1, -1, -1):
                    state = states[position + 1]
                    previous = states[position]
                    update_gate = updates[position]
                    reset_gate = resets[position]
                    candidate_state = candidates[position]

                    dy = probabilities[position].copy()
                    dy[int(targets[position])] -= np.float32(1.0)
                    d_output += np.outer(state, dy).astype(np.float32)
                    d_output_bias += dy

                    dh = (dy @ output.T + dh_next).astype(np.float32)
                    d_candidate_state = (
                        dh * (np.float32(1.0) - update_gate)
                    ).astype(np.float32)
                    d_update_gate = (
                        dh * (previous - candidate_state)
                    ).astype(np.float32)
                    dh_previous = (dh * update_gate).astype(np.float32)

                    da_candidate = (
                        d_candidate_state
                        * (
                            np.float32(1.0)
                            - candidate_state * candidate_state
                        )
                    ).astype(np.float32)
                    reset_previous = reset_gate * previous
                    d_candidate += np.outer(
                        reset_previous,
                        da_candidate,
                    ).astype(np.float32)
                    d_candidate_bias += da_candidate
                    d_reset_previous = (
                        da_candidate @ candidate_recurrent.T
                    ).astype(np.float32)
                    d_reset_gate = (
                        d_reset_previous * previous
                    ).astype(np.float32)
                    dh_previous += d_reset_previous * reset_gate

                    da_reset = (
                        d_reset_gate
                        * reset_gate
                        * (np.float32(1.0) - reset_gate)
                    ).astype(np.float32)
                    d_reset += np.outer(
                        previous,
                        da_reset,
                    ).astype(np.float32)
                    d_reset_bias += da_reset
                    dh_previous += (
                        da_reset @ reset_recurrent.T
                    ).astype(np.float32)

                    da_update = (
                        d_update_gate
                        * update_gate
                        * (np.float32(1.0) - update_gate)
                    ).astype(np.float32)
                    d_update += np.outer(
                        previous,
                        da_update,
                    ).astype(np.float32)
                    d_update_bias += da_update
                    dh_previous += (
                        da_update @ update_recurrent.T
                    ).astype(np.float32)

                    token_index = int(inputs[position])
                    embedding_gradient = (
                        da_candidate + da_reset + da_update
                    ).astype(np.float32)
                    prior = d_embedding_rows.get(token_index)
                    if prior is None:
                        d_embedding_rows[token_index] = (
                            embedding_gradient.copy()
                        )
                    else:
                        prior += embedding_gradient
                    dh_next[:] = dh_previous

                normalizer = np.float32(
                    1.0 / max(1, len(inputs))
                )
                for gradient in gradients:
                    gradient *= normalizer
                    np.clip(
                        gradient,
                        -5.0,
                        5.0,
                        out=gradient,
                    )
                for token_index, gradient in d_embedding_rows.items():
                    gradient *= normalizer
                    np.clip(
                        gradient,
                        -5.0,
                        5.0,
                        out=gradient,
                    )
                    previous = acc_embedding_rows.get(token_index)
                    if previous is None:
                        acc_embedding_rows[token_index] = gradient.copy()
                    else:
                        previous += gradient
                for target, gradient in zip(
                    accumulated,
                    gradients,
                    strict=True,
                ):
                    target += gradient
                accumulated_sequences += 1
                if accumulated_sequences >= accumulation_steps:
                    flush()

            flush()
            epochs_completed += 1
            average_loss = epoch_loss / max(1, epoch_targets)
            loss_history.append(float(average_loss))
            if early_stopping_patience:
                if math.isinf(best_loss):
                    best_loss = average_loss
                    stale_epochs = 0
                else:
                    required = best_loss * min_improvement
                    improvement = best_loss - average_loss
                    if improvement > required:
                        best_loss = average_loss
                        stale_epochs = 0
                    else:
                        stale_epochs += 1
                        if stale_epochs >= early_stopping_patience:
                            stopped_early = True
                            break

        model = cls(
            model_id=model_id,
            vocab=vocab,
            hidden_size=hidden,
            embedding=embedding,
            update_recurrent=update_recurrent,
            update_bias=update_bias,
            reset_recurrent=reset_recurrent,
            reset_bias=reset_bias,
            candidate_recurrent=candidate_recurrent,
            candidate_bias=candidate_bias,
            output=output,
            output_bias=output_bias,
            temperature=temp,
        )
        model.training_epochs_completed = epochs_completed
        model.training_loss_history = tuple(loss_history)
        model.training_stopped_early = stopped_early
        model.training_examples = len(sequences)
        model.training_tokens = total_training_tokens
        model.training_optimizer_steps = optimizer_steps
        model.training_gradient_accumulation_steps = accumulation_steps
        return model

    def _token_id(self, token: str) -> int:
        return self._token_to_id.get(token, 0)

    def _advance(
        self,
        hidden: np.ndarray,
        token_id: int,
    ) -> np.ndarray:
        x = self.embedding[token_id]
        update_gate = _sigmoid(
            x + hidden @ self.update_recurrent + self.update_bias
        )
        reset_gate = _sigmoid(
            x + hidden @ self.reset_recurrent + self.reset_bias
        )
        candidate_state = np.tanh(
            x
            + (reset_gate * hidden) @ self.candidate_recurrent
            + self.candidate_bias
        ).astype(np.float32)
        return (
            (np.float32(1.0) - update_gate) * candidate_state
            + update_gate * hidden
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
        probability = exp / max(float(exp.sum()), 1e-12)
        return int(rng.choice(self.vocab_size, p=probability))

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
        recurrent_cost = max(
            1,
            3 * self.hidden_size * self.hidden_size,
        )
        generation_cost = max(
            1,
            recurrent_cost + self.hidden_size * self.vocab_size,
        )
        generation_limit = min(
            request.max_output_tokens,
            max(
                1,
                (_MAX_INFERENCE_WORK // 2) // generation_cost,
            ),
        )
        remaining = max(
            1,
            _MAX_INFERENCE_WORK
            - generation_limit * generation_cost,
        )
        context_limit = min(
            _MAX_SEQUENCE_TOKENS,
            max(1, remaining // recurrent_cost),
        )
        input_tokens = list(
            _tokenize(request.rendered_input)
        )[-context_limit:]
        hidden = np.zeros(self.hidden_size, dtype=np.float32)
        for token in input_tokens:
            if cancel.is_set():
                raise LocalInferenceCancelled(
                    "local gated recurrent inference cancelled"
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
                    "local gated recurrent inference cancelled"
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

        text = _detokenize(generated)
        if not text:
            text = (
                "I do not have enough learned local context "
                "to answer."
            )
        response_id = "local-gru:" + _digest(
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
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


__all__ = ["NumpyGatedRecurrentLM"]
