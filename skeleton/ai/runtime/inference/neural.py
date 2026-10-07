"""Credential-free native neural language-model baseline.

This is a compact recurrent neural LM implemented with NumPy so Skeleton owns a
real learned-weight training/inference path beyond the reference n-gram witness.
It is intentionally a portable baseline, not a quality/SI claim. Production
architectures can implement the same LocalModelBackend contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import threading
import time
from typing import Any, Mapping, Sequence

import numpy as np

from skeleton.ai.runtime.inference.local import (
    LocalInferenceCancelled,
    LocalInferenceRequest,
    LocalInferenceResult,
)


BOS = 256
EOS = 257
VOCAB_SIZE = 258


class NeuralLMError(RuntimeError):
    """Native neural language-model state is invalid or non-reproducible."""


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest_parts(parts: Sequence[bytes]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(len(part).to_bytes(8, "big"))
        h.update(part)
    return h.hexdigest()


def _encode(text: str) -> tuple[int, ...]:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return tuple(text.encode("utf-8", errors="strict"))


def _decode(tokens: Sequence[int]) -> str:
    raw = bytes(token for token in tokens if 0 <= token <= 255)
    return raw.decode("utf-8", errors="replace")


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    exps = np.exp(shifted)
    total = float(np.sum(exps))
    if not math.isfinite(total) or total <= 0:
        raise NeuralLMError("non-finite softmax normalization")
    return exps / total


@dataclass(frozen=True, slots=True)
class NeuralLMConfig:
    hidden_size: int = 48
    seed: int = 0
    dtype: str = "float64"

    def __post_init__(self) -> None:
        if (
            isinstance(self.hidden_size, bool)
            or not isinstance(self.hidden_size, int)
            or not 4 <= self.hidden_size <= 2048
        ):
            raise NeuralLMError("hidden_size must be in [4, 2048]")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise NeuralLMError("seed must be an integer")
        if self.dtype not in {"float64"}:
            raise NeuralLMError("portable baseline requires float64")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.numpy_recurrent_lm_config.v1",
            "hidden_size": self.hidden_size,
            "seed": self.seed,
            "dtype": self.dtype,
            "vocab_size": VOCAB_SIZE,
            "bos_token": BOS,
            "eos_token": EOS,
            "representation": "utf8-byte-v1",
        }


@dataclass(frozen=True, slots=True)
class NeuralTrainingReceipt:
    model_id: str
    initial_model_digest: str
    final_model_digest: str
    corpus_digest: str
    epochs: int
    learning_rate: float
    sequence_count: int
    token_count: int
    initial_loss: float
    final_loss: float
    gradient_clip: float

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            _stable_json(
                {
                    "schema_version": "skeleton.neural_training_receipt.v1",
                    "model_id": self.model_id,
                    "initial_model_digest": self.initial_model_digest,
                    "final_model_digest": self.final_model_digest,
                    "corpus_digest": self.corpus_digest,
                    "epochs": self.epochs,
                    "learning_rate": self.learning_rate,
                    "sequence_count": self.sequence_count,
                    "token_count": self.token_count,
                    "initial_loss": self.initial_loss,
                    "final_loss": self.final_loss,
                    "gradient_clip": self.gradient_clip,
                }
            ).encode("utf-8")
        ).hexdigest()


class NumpyRecurrentLM:
    """Small byte-level Elman RNN with deterministic local training."""

    def __init__(
        self,
        *,
        model_id: str = "skeleton-numpy-rnn-v1",
        config: NeuralLMConfig | None = None,
        parameters: Mapping[str, np.ndarray] | None = None,
    ) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            raise NeuralLMError("model_id must be non-empty")
        self.model_id = model_id.strip()
        self.config = config or NeuralLMConfig()
        h = self.config.hidden_size

        if parameters is None:
            rng = np.random.default_rng(self.config.seed)
            scale = 0.05
            self.embedding = rng.normal(0.0, scale, (VOCAB_SIZE, h)).astype(np.float64)
            self.recurrent = rng.normal(0.0, scale, (h, h)).astype(np.float64)
            self.hidden_bias = np.zeros((h,), dtype=np.float64)
            self.output = rng.normal(0.0, scale, (h, VOCAB_SIZE)).astype(np.float64)
            self.output_bias = np.zeros((VOCAB_SIZE,), dtype=np.float64)
        else:
            expected = {
                "embedding": (VOCAB_SIZE, h),
                "recurrent": (h, h),
                "hidden_bias": (h,),
                "output": (h, VOCAB_SIZE),
                "output_bias": (VOCAB_SIZE,),
            }
            loaded: dict[str, np.ndarray] = {}
            for name, shape in expected.items():
                if name not in parameters:
                    raise NeuralLMError(f"missing parameter {name}")
                value = np.asarray(parameters[name], dtype=np.float64)
                if value.shape != shape:
                    raise NeuralLMError(f"parameter {name} shape mismatch")
                if not np.all(np.isfinite(value)):
                    raise NeuralLMError(f"parameter {name} contains non-finite values")
                loaded[name] = value.copy()
            self.embedding = loaded["embedding"]
            self.recurrent = loaded["recurrent"]
            self.hidden_bias = loaded["hidden_bias"]
            self.output = loaded["output"]
            self.output_bias = loaded["output_bias"]

    @property
    def model_digest(self) -> str:
        parts = [
            _stable_json(self.config.as_dict()).encode("utf-8"),
            self.model_id.encode("utf-8"),
        ]
        for value in (
            self.embedding,
            self.recurrent,
            self.hidden_bias,
            self.output,
            self.output_bias,
        ):
            canonical = np.asarray(value, dtype="<f8", order="C")
            parts.append(str(canonical.shape).encode("ascii"))
            parts.append(canonical.tobytes(order="C"))
        return _digest_parts(parts)

    @staticmethod
    def _corpus_digest(corpus: Sequence[str]) -> str:
        if not corpus:
            raise NeuralLMError("training corpus must not be empty")
        docs: list[str] = []
        for document in corpus:
            if not isinstance(document, str) or not document:
                raise NeuralLMError("training documents must be non-empty text")
            docs.append(document)
        return hashlib.sha256(
            _stable_json(
                {"schema_version": "skeleton.neural_corpus.v1", "documents": docs}
            ).encode("utf-8")
        ).hexdigest()

    def _sequence(self, document: str) -> tuple[int, ...]:
        return (BOS,) + _encode(document) + (EOS,)

    def _forward(
        self,
        inputs: Sequence[int],
    ) -> tuple[list[np.ndarray], list[np.ndarray]]:
        h = np.zeros((self.config.hidden_size,), dtype=np.float64)
        states = [h.copy()]
        probabilities: list[np.ndarray] = []
        for token in inputs:
            h = np.tanh(self.embedding[token] + h @ self.recurrent + self.hidden_bias)
            probs = _softmax(h @ self.output + self.output_bias)
            states.append(h.copy())
            probabilities.append(probs)
        return states, probabilities

    def loss(self, corpus: Sequence[str]) -> float:
        total = 0.0
        count = 0
        for document in corpus:
            seq = self._sequence(document)
            _, probs = self._forward(seq[:-1])
            for probability, target in zip(probs, seq[1:]):
                total -= math.log(max(float(probability[target]), 1e-300))
                count += 1
        if count == 0:
            raise NeuralLMError("corpus produced no training targets")
        return total / count

    def train(
        self,
        corpus: Sequence[str],
        *,
        epochs: int = 8,
        learning_rate: float = 0.05,
        gradient_clip: float = 1.0,
    ) -> NeuralTrainingReceipt:
        if isinstance(epochs, bool) or not isinstance(epochs, int) or not 1 <= epochs <= 10000:
            raise NeuralLMError("epochs must be in [1, 10000]")
        if not isinstance(learning_rate, (int, float)) or isinstance(learning_rate, bool):
            raise NeuralLMError("learning_rate must be numeric")
        if not 0.0 < float(learning_rate) <= 10.0:
            raise NeuralLMError("learning_rate must be in (0, 10]")
        if not isinstance(gradient_clip, (int, float)) or isinstance(gradient_clip, bool):
            raise NeuralLMError("gradient_clip must be numeric")
        if not 0.0 < float(gradient_clip) <= 1000.0:
            raise NeuralLMError("gradient_clip must be in (0, 1000]")

        documents = tuple(corpus)
        corpus_digest = self._corpus_digest(documents)
        initial_digest = self.model_digest
        initial_loss = self.loss(documents)
        lr = float(learning_rate)
        clip = float(gradient_clip)
        total_tokens = sum(len(self._sequence(document)) - 1 for document in documents)

        for _ in range(epochs):
            for document in documents:
                seq = self._sequence(document)
                inputs = seq[:-1]
                targets = seq[1:]
                states, probabilities = self._forward(inputs)

                grad_embedding = np.zeros_like(self.embedding)
                grad_recurrent = np.zeros_like(self.recurrent)
                grad_hidden_bias = np.zeros_like(self.hidden_bias)
                grad_output = np.zeros_like(self.output)
                grad_output_bias = np.zeros_like(self.output_bias)
                dh_next = np.zeros((self.config.hidden_size,), dtype=np.float64)

                for step in range(len(inputs) - 1, -1, -1):
                    probs = probabilities[step].copy()
                    probs[targets[step]] -= 1.0
                    hidden = states[step + 1]
                    prev_hidden = states[step]

                    grad_output += np.outer(hidden, probs)
                    grad_output_bias += probs

                    dh = probs @ self.output.T + dh_next
                    dz = dh * (1.0 - hidden * hidden)
                    grad_embedding[inputs[step]] += dz
                    grad_recurrent += np.outer(prev_hidden, dz)
                    grad_hidden_bias += dz
                    dh_next = dz @ self.recurrent.T

                norm_sq = 0.0
                grads = (
                    grad_embedding,
                    grad_recurrent,
                    grad_hidden_bias,
                    grad_output,
                    grad_output_bias,
                )
                for grad in grads:
                    norm_sq += float(np.sum(grad * grad))
                norm = math.sqrt(norm_sq)
                scale = 1.0 if norm <= clip else clip / max(norm, 1e-300)

                self.embedding -= lr * scale * grad_embedding
                self.recurrent -= lr * scale * grad_recurrent
                self.hidden_bias -= lr * scale * grad_hidden_bias
                self.output -= lr * scale * grad_output
                self.output_bias -= lr * scale * grad_output_bias

                for value in (
                    self.embedding,
                    self.recurrent,
                    self.hidden_bias,
                    self.output,
                    self.output_bias,
                ):
                    if not np.all(np.isfinite(value)):
                        raise NeuralLMError("training produced non-finite parameters")

        final_loss = self.loss(documents)
        return NeuralTrainingReceipt(
            model_id=self.model_id,
            initial_model_digest=initial_digest,
            final_model_digest=self.model_digest,
            corpus_digest=corpus_digest,
            epochs=epochs,
            learning_rate=lr,
            sequence_count=len(documents),
            token_count=total_tokens,
            initial_loss=initial_loss,
            final_loss=final_loss,
            gradient_clip=clip,
        )

    def _prime(self, tokens: Sequence[int]) -> np.ndarray:
        h = np.zeros((self.config.hidden_size,), dtype=np.float64)
        for token in tokens:
            h = np.tanh(self.embedding[token] + h @ self.recurrent + self.hidden_bias)
        return h

    def infer(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        start = time.perf_counter()
        prompt_tokens = (BOS,) + _encode(request.prompt)
        hidden = self._prime(prompt_tokens)
        rng = np.random.default_rng(
            (request.seed ^ int(self.model_digest[:16], 16)) & ((1 << 63) - 1)
        )
        output_tokens: list[int] = []
        finish = "length"

        for _ in range(request.max_output_tokens):
            if cancel.is_set():
                raise LocalInferenceCancelled("native neural generation cancelled")
            probs = _softmax(hidden @ self.output + self.output_bias)
            token = int(rng.choice(VOCAB_SIZE, p=probs))
            if token == EOS:
                finish = "completed"
                break
            if token != BOS:
                output_tokens.append(token)
            hidden = np.tanh(
                self.embedding[token] + hidden @ self.recurrent + self.hidden_bias
            )
            text = _decode(output_tokens)
            if any(text.endswith(marker) for marker in request.stop):
                finish = "completed"
                break

        text = _decode(output_tokens)
        if not text:
            text = " "
        response_id = "local-neural:" + hashlib.sha256(
            _stable_json(
                {
                    "model": self.model_digest,
                    "request": request.digest,
                    "output": output_tokens,
                }
            ).encode("utf-8")
        ).hexdigest()[:32]
        return LocalInferenceResult(
            text=text,
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=len(prompt_tokens),
            output_tokens=len(output_tokens),
            finish_reason=finish,
            response_id=response_id,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.numpy_recurrent_lm.v1",
            "model_id": self.model_id,
            "config": self.config.as_dict(),
            "parameters": {
                "embedding": self.embedding.tolist(),
                "recurrent": self.recurrent.tolist(),
                "hidden_bias": self.hidden_bias.tolist(),
                "output": self.output.tolist(),
                "output_bias": self.output_bias.tolist(),
            },
            "model_digest": self.model_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NumpyRecurrentLM":
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        if payload.get("schema_version") != "skeleton.numpy_recurrent_lm.v1":
            raise NeuralLMError("unsupported neural model schema")

        model_id = payload.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise NeuralLMError("serialized model_id must be non-empty text")

        config_payload = payload.get("config")
        if not isinstance(config_payload, Mapping):
            raise NeuralLMError("model config is missing")
        hidden_size = config_payload.get("hidden_size")
        seed = config_payload.get("seed")
        dtype = config_payload.get("dtype")
        if isinstance(hidden_size, bool) or not isinstance(hidden_size, int):
            raise NeuralLMError("serialized hidden_size must be an integer")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise NeuralLMError("serialized seed must be an integer")
        if not isinstance(dtype, str):
            raise NeuralLMError("serialized dtype must be text")
        config = NeuralLMConfig(
            hidden_size=hidden_size,
            seed=seed,
            dtype=dtype,
        )
        if dict(config_payload) != config.as_dict():
            raise NeuralLMError("serialized representation/config identity mismatch")

        raw_params = payload.get("parameters")
        if not isinstance(raw_params, Mapping):
            raise NeuralLMError("model parameters are missing")
        expected_parameter_names = {
            "embedding",
            "recurrent",
            "hidden_bias",
            "output",
            "output_bias",
        }
        if set(raw_params) != expected_parameter_names:
            raise NeuralLMError("serialized parameter set mismatch")

        model = cls(
            model_id=model_id,
            config=config,
            parameters={
                name: np.asarray(value, dtype=np.float64)
                for name, value in raw_params.items()
            },
        )
        claimed = payload.get("model_digest")
        if not isinstance(claimed, str) or claimed != model.model_digest:
            raise NeuralLMError("serialized neural model digest mismatch")
        return model


__all__ = [
    "BOS",
    "EOS",
    "VOCAB_SIZE",
    "NeuralLMConfig",
    "NeuralLMError",
    "NeuralTrainingReceipt",
    "NumpyRecurrentLM",
]
