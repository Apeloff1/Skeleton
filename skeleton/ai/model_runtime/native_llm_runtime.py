"""Production-oriented native LLM runtime over Skeleton's causal transformer.

The cortex owns the mathematical model: token embeddings, positional vectors,
stacked causal attention, RoPE, feed-forward blocks, unembedding, training, an
incremental KV cache and an optional Torch/CUDA harness. This module is the
governed execution plane around that engine. It makes the path from text ->
token IDs -> embeddings -> transformer -> logits -> sampling -> text explicit,
bounded, replayable, checkpointable, portable and observable.

No provider credentials or network authority live here.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import random
import threading
from typing import Any, Iterable, Mapping, Sequence

from skeleton.cortex.attn import sample_logits, softmax
from skeleton.cortex.transformer import KVCache, TinyTransformer

from .flgb_model_runtime import MAX_BATCH_SIZE, MAX_TOKENS, ModelRuntimeError
from .tokenization import NativeTokenizer, TokenSequence, TokenizerState

RUNTIME_SCHEMA = "skeleton.ai.native-llm-runtime.v2"
CHECKPOINT_SCHEMA = "skeleton.ai.native-llm-checkpoint.v2"
MAX_TRACE_CAPACITY = 100_000
MAX_MODEL_BYTES_HARD = 2**63 - 1


class RuntimeContractError(ModelRuntimeError):
    """Fail-closed native runtime contract violation."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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
        raise RuntimeContractError("value is not canonical-json encodable") from exc


def _digest(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _text_digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _require_digest(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise RuntimeContractError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class RuntimeLimits:
    """Non-negotiable admission bounds for one runtime instance."""

    max_context_tokens: int
    max_output_tokens: int = 4096
    max_batch_size: int = 64
    max_batch_tokens: int = 262_144
    max_model_bytes: int = 8 * 1024**3
    max_kv_bytes: int = 2 * 1024**3
    trace_capacity: int = 4096

    def __post_init__(self) -> None:
        ints = {
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_batch_size": self.max_batch_size,
            "max_batch_tokens": self.max_batch_tokens,
            "max_model_bytes": self.max_model_bytes,
            "max_kv_bytes": self.max_kv_bytes,
            "trace_capacity": self.trace_capacity,
        }
        if any(not _is_int(value) or value <= 0 for value in ints.values()):
            raise RuntimeContractError("runtime limits must be positive integers")
        if self.max_context_tokens > MAX_TOKENS or self.max_output_tokens > MAX_TOKENS:
            raise RuntimeContractError("runtime token limit exceeds hard bound")
        if self.max_batch_size > MAX_BATCH_SIZE:
            raise RuntimeContractError("runtime batch size exceeds hard bound")
        if self.max_batch_tokens > MAX_TOKENS * MAX_BATCH_SIZE:
            raise RuntimeContractError("runtime aggregate batch budget exceeds hard bound")
        if self.max_model_bytes > MAX_MODEL_BYTES_HARD or self.max_kv_bytes > MAX_MODEL_BYTES_HARD:
            raise RuntimeContractError("runtime memory limit exceeds hard bound")
        if self.trace_capacity > MAX_TRACE_CAPACITY:
            raise RuntimeContractError("runtime trace capacity exceeds hard bound")

    def to_dict(self) -> dict[str, int]:
        return {
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_batch_size": self.max_batch_size,
            "max_batch_tokens": self.max_batch_tokens,
            "max_model_bytes": self.max_model_bytes,
            "max_kv_bytes": self.max_kv_bytes,
            "trace_capacity": self.trace_capacity,
        }


@dataclass(frozen=True)
class SamplingConfig:
    max_new_tokens: int = 32
    seed: int = 0
    temperature: float = 1.0
    top_k: int = 0
    top_p: float = 1.0
    use_cache: bool = True
    context_policy: str = "reject"
    stop_token_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not _is_int(self.max_new_tokens) or self.max_new_tokens < 0:
            raise RuntimeContractError("max_new_tokens must be a non-negative integer")
        if not _is_int(self.seed):
            raise RuntimeContractError("seed must be an integer")
        if isinstance(self.temperature, bool) or not isinstance(self.temperature, (int, float)):
            raise RuntimeContractError("temperature must be numeric")
        if not math.isfinite(float(self.temperature)) or float(self.temperature) <= 0.0:
            raise RuntimeContractError("temperature must be finite and positive")
        if not _is_int(self.top_k) or self.top_k < 0:
            raise RuntimeContractError("top_k must be a non-negative integer")
        if isinstance(self.top_p, bool) or not isinstance(self.top_p, (int, float)):
            raise RuntimeContractError("top_p must be numeric")
        if not math.isfinite(float(self.top_p)) or not 0.0 < float(self.top_p) <= 1.0:
            raise RuntimeContractError("top_p must be in (0, 1]")
        if not isinstance(self.use_cache, bool):
            raise RuntimeContractError("use_cache must be boolean")
        if self.context_policy not in {"reject", "truncate-left"}:
            raise RuntimeContractError("unsupported context policy")
        stops = tuple(self.stop_token_ids)
        if len(stops) != len(set(stops)):
            raise RuntimeContractError("duplicate stop token id")
        if any(not _is_int(token_id) or token_id < 0 for token_id in stops):
            raise RuntimeContractError("invalid stop token id")
        object.__setattr__(self, "stop_token_ids", stops)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_new_tokens": self.max_new_tokens,
            "seed": self.seed,
            "temperature": float(self.temperature),
            "top_k": self.top_k,
            "top_p": float(self.top_p),
            "use_cache": self.use_cache,
            "context_policy": self.context_policy,
            "stop_token_ids": list(self.stop_token_ids),
        }


GenerationConfig = SamplingConfig


@dataclass(frozen=True)
class RuntimeMemoryReport:
    parameter_count: int
    numeric_model_bytes: int
    kv_payload_bytes: int
    total_numeric_bytes: int

    def to_dict(self) -> dict[str, int]:
        return {
            "parameter_count": self.parameter_count,
            "numeric_model_bytes": self.numeric_model_bytes,
            "kv_payload_bytes": self.kv_payload_bytes,
            "total_numeric_bytes": self.total_numeric_bytes,
        }


@dataclass(frozen=True)
class RuntimeEvent:
    sequence: int
    kind: str
    request_digest: str | None
    fields: tuple[tuple[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "request_digest": self.request_digest,
            "fields": {key: value for key, value in self.fields},
        }


@dataclass(frozen=True)
class ForwardPass:
    token_sequence: TokenSequence
    last_hidden: tuple[float, ...]
    logits: tuple[float, ...]
    probabilities: tuple[float, ...]
    model_digest: str


@dataclass(frozen=True)
class InferenceReceipt:
    request_digest: str
    model_digest: str
    tokenizer_digest: str
    prompt_digest: str
    prompt_tokens: int
    generated_token_ids: tuple[int, ...]
    output_digest: str
    sampling_digest: str
    cache_requested: bool
    cache_used: bool
    context_truncated: bool
    actual_device: str
    trace_digest: str

    def __post_init__(self) -> None:
        for name in (
            "request_digest",
            "model_digest",
            "tokenizer_digest",
            "prompt_digest",
            "output_digest",
            "sampling_digest",
            "trace_digest",
        ):
            _require_digest(getattr(self, name), name)
        if not _is_int(self.prompt_tokens) or self.prompt_tokens <= 0:
            raise RuntimeContractError("invalid prompt token count")
        if any(not _is_int(token_id) or token_id < 0 for token_id in self.generated_token_ids):
            raise RuntimeContractError("invalid generated token id")
        if not isinstance(self.cache_requested, bool) or not isinstance(self.cache_used, bool):
            raise RuntimeContractError("cache receipt flags must be boolean")
        if not isinstance(self.context_truncated, bool):
            raise RuntimeContractError("context_truncated must be boolean")
        if not isinstance(self.actual_device, str) or not self.actual_device:
            raise RuntimeContractError("actual_device required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_digest": self.request_digest,
            "model_digest": self.model_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "prompt_digest": self.prompt_digest,
            "prompt_tokens": self.prompt_tokens,
            "generated_token_ids": list(self.generated_token_ids),
            "output_digest": self.output_digest,
            "sampling_digest": self.sampling_digest,
            "cache_requested": self.cache_requested,
            "cache_used": self.cache_used,
            "context_truncated": self.context_truncated,
            "actual_device": self.actual_device,
            "trace_digest": self.trace_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InferenceReceipt":
        if not isinstance(value, Mapping):
            raise RuntimeContractError("inference receipt mapping required")
        expected = {
            "request_digest", "model_digest", "tokenizer_digest",
            "prompt_digest", "prompt_tokens", "generated_token_ids",
            "output_digest", "sampling_digest", "cache_requested",
            "cache_used", "context_truncated", "actual_device",
            "trace_digest",
        }
        if set(value) != expected:
            raise RuntimeContractError("inference receipt fields drifted")
        return cls(
            request_digest=value["request_digest"],
            model_digest=value["model_digest"],
            tokenizer_digest=value["tokenizer_digest"],
            prompt_digest=value["prompt_digest"],
            prompt_tokens=value["prompt_tokens"],
            generated_token_ids=tuple(value["generated_token_ids"]),
            output_digest=value["output_digest"],
            sampling_digest=value["sampling_digest"],
            cache_requested=value["cache_requested"],
            cache_used=value["cache_used"],
            context_truncated=value["context_truncated"],
            actual_device=value["actual_device"],
            trace_digest=value["trace_digest"],
        )

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "request_digest": self.request_digest,
            "model_digest": self.model_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "prompt_digest": self.prompt_digest,
            "prompt_tokens": self.prompt_tokens,
            "generated_token_ids": list(self.generated_token_ids),
            "output_digest": self.output_digest,
            "sampling_digest": self.sampling_digest,
            "cache_requested": self.cache_requested,
            "context_truncated": self.context_truncated,
        }

    @property
    def semantic_digest(self) -> str:
        return _digest(self.semantic_dict())

    @property
    def audit_digest(self) -> str:
        return _digest({
            **self.semantic_dict(),
            "cache_used": self.cache_used,
            "actual_device": self.actual_device,
            "trace_digest": self.trace_digest,
        })


@dataclass(frozen=True)
class GenerationResult:
    prompt_sequence: TokenSequence
    generated_token_ids: tuple[int, ...]
    generated_tokens: tuple[str, ...]
    text: str
    receipt: InferenceReceipt

    @property
    def prompt_ids(self) -> tuple[int, ...]:
        return self.prompt_sequence.token_ids

    @property
    def output_tokens(self) -> tuple[str, ...]:
        return self.generated_tokens

    @property
    def checkpoint_digest(self) -> str:
        return self.receipt.model_digest


@dataclass(frozen=True)
class InferenceRequest:
    request_id: str
    prompt: str
    sampling: SamplingConfig = field(default_factory=SamplingConfig)

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id or len(self.request_id) > 256:
            raise RuntimeContractError("invalid request_id")
        if not isinstance(self.prompt, str):
            raise RuntimeContractError("prompt must be a string")
        if not isinstance(self.sampling, SamplingConfig):
            raise RuntimeContractError("SamplingConfig required")


class NativeLLMRuntime:
    """Bounded, deterministic execution plane for TinyTransformer."""

    def __init__(
        self,
        model: TinyTransformer,
        *,
        limits: RuntimeLimits | None = None,
        max_context: int | None = None,
        device: str | None = None,
        allow_device_fallback: bool = True,
    ) -> None:
        if not isinstance(model, TinyTransformer):
            raise RuntimeContractError("TinyTransformer required")
        default_context = int(max_context or model.ctx)
        self.model = model
        self.limits = limits or RuntimeLimits(max_context_tokens=default_context)
        if max_context is not None and int(max_context) != self.limits.max_context_tokens:
            raise RuntimeContractError("max_context conflicts with RuntimeLimits")
        if self.limits.max_context_tokens > model.ctx:
            raise RuntimeContractError("runtime context exceeds model positional capacity")
        self.tokenizer = NativeTokenizer(model)
        self._lock = threading.RLock()
        self._events: deque[RuntimeEvent] = deque(maxlen=self.limits.trace_capacity)
        self._event_sequence = 0
        self._metrics = {
            "requests": 0,
            "prompt_tokens": 0,
            "generated_tokens": 0,
            "cache_requests": 0,
            "cache_uses": 0,
            "context_truncations": 0,
            "replays": 0,
        }
        self._validate_runtime_model()
        self._admit_memory(use_cache=True)
        if device is not None:
            self.bind_device(device, allow_fallback=allow_device_fallback)
        self._emit(
            "runtime_ready",
            None,
            model_digest=self.model_digest,
            tokenizer_digest=self.tokenizer.digest,
            device=self.actual_device,
        )

    @property
    def max_context(self) -> int:
        return self.limits.max_context_tokens

    @property
    def actual_device(self) -> str:
        return str(getattr(self.model, "device", "cpu") or "cpu")

    @property
    def model_digest(self) -> str:
        return _digest(self._semantic_model_snapshot())

    @property
    def tokenizer_digest(self) -> str:
        return self.tokenizer.digest

    def _semantic_model_snapshot(self) -> dict[str, Any]:
        snapshot = dict(self.model.snapshot())
        snapshot.pop("device", None)
        snapshot.pop("resident", None)
        return snapshot

    def execution_graph(self) -> tuple[str, ...]:
        nodes = ["tokenize", "token-embedding+position"]
        for index, layer in enumerate(self.model.layers):
            nodes.append(f"layer[{index}].causal-mha-rope")
            if layer.d_ff:
                nodes.append(f"layer[{index}].{layer.ffn_kind}-ffn")
        nodes.extend(("unembed", "sample", "decode"))
        return tuple(nodes)

    def _emit(self, kind: str, request_digest: str | None, **fields: Any) -> RuntimeEvent:
        self._event_sequence += 1
        event = RuntimeEvent(
            self._event_sequence,
            str(kind),
            request_digest,
            tuple(sorted(fields.items(), key=lambda item: item[0])),
        )
        self._events.append(event)
        return event

    def events(self) -> tuple[RuntimeEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def metrics(self) -> Mapping[str, int]:
        with self._lock:
            return dict(self._metrics)

    def _trace_since(self, sequence: int, request_digest: str) -> tuple[RuntimeEvent, ...]:
        return tuple(
            event for event in self._events
            if event.sequence > sequence and event.request_digest == request_digest
        )

    @staticmethod
    def _count_numeric_payload(value: Any, seen: set[int] | None = None) -> int:
        seen = seen if seen is not None else set()
        if isinstance(value, bool) or value is None or isinstance(value, str):
            return 0
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                raise RuntimeContractError("model contains non-finite numeric value")
            return 1
        if isinstance(value, (list, tuple)):
            ident = id(value)
            if ident in seen:
                return 0
            seen.add(ident)
            return sum(NativeLLMRuntime._count_numeric_payload(item, seen) for item in value)
        if isinstance(value, Mapping):
            ident = id(value)
            if ident in seen:
                return 0
            seen.add(ident)
            return sum(NativeLLMRuntime._count_numeric_payload(item, seen) for item in value.values())
        raise RuntimeContractError("model snapshot contains unsupported value")

    def memory_report(self) -> RuntimeMemoryReport:
        snapshot = self._semantic_model_snapshot()
        parameter_count = self._count_numeric_payload(snapshot)
        model_bytes = parameter_count * 8
        kv_bytes = (
            self.model.n_layers
            * self.limits.max_context_tokens
            * 2
            * self.model.dim
            * 8
        )
        return RuntimeMemoryReport(
            parameter_count,
            model_bytes,
            kv_bytes,
            model_bytes + kv_bytes,
        )

    def _admit_memory(self, *, use_cache: bool) -> RuntimeMemoryReport:
        report = self.memory_report()
        if report.numeric_model_bytes > self.limits.max_model_bytes:
            raise RuntimeContractError("model numeric payload exceeds runtime memory budget")
        if use_cache and report.kv_payload_bytes > self.limits.max_kv_bytes:
            raise RuntimeContractError("KV payload exceeds runtime memory budget")
        return report

    def _validate_runtime_model(self) -> None:
        if self.model.ctx < 2 or self.model.dim < 1 or self.model.n_layers < 1:
            raise RuntimeContractError("invalid model geometry")
        if len(self.model.itos) != len(self.model.E) or len(self.model.itos) != len(self.model.Wout):
            raise RuntimeContractError("vocabulary/embedding/unembedding size mismatch")
        if len(self.model.P) < self.model.ctx:
            raise RuntimeContractError("positional table shorter than model context")
        if any(len(row) != self.model.dim for row in self.model.E):
            raise RuntimeContractError("token embedding dimension mismatch")
        if any(len(row) != self.model.dim for row in self.model.P[: self.model.ctx]):
            raise RuntimeContractError("positional embedding dimension mismatch")
        if any(len(row) != self.model.dim for row in self.model.Wout):
            raise RuntimeContractError("unembedding dimension mismatch")
        if len(self.model.bout) != len(self.model.itos):
            raise RuntimeContractError("unembedding bias size mismatch")
        if self.model.dim % self.model.n_heads:
            raise RuntimeContractError("attention head dimension mismatch")
        self._count_numeric_payload(self._semantic_model_snapshot())

    def bind_device(self, device: str, *, allow_fallback: bool = True) -> Mapping[str, Any]:
        if (
            not isinstance(device, str)
            or device.lower() not in {"auto", "cpu", "cuda", "gpu", "torch", "torch-cpu"}
        ):
            raise RuntimeContractError("unsupported device request")
        requested = device.lower()
        with self._lock:
            self.model.to(requested)
            actual = self.actual_device
            expects_cuda = requested in {"cuda", "gpu"}
            if expects_cuda and actual != "cuda" and not allow_fallback:
                raise RuntimeContractError("requested CUDA device unavailable")
            self._emit(
                "device_bound",
                None,
                requested=requested,
                actual=actual,
                resident=bool(getattr(self.model, "resident", False)),
            )
            return {
                "requested": requested,
                "actual": actual,
                "resident": bool(getattr(self.model, "resident", False)),
                "degraded": expects_cuda and actual != "cuda",
            }

    def encode(self, text: str) -> tuple[int, ...]:
        return self.tokenizer.encode_ids(text)

    def tokenize(self, text: str) -> TokenSequence:
        return self.tokenizer.encode(text)

    def decode(self, token_ids: Sequence[int]) -> str:
        return self.tokenizer.decode_ids(token_ids)

    def embed_ids(self, token_ids: Sequence[int]) -> tuple[tuple[float, ...], ...]:
        ids = tuple(token_ids)
        if not ids:
            raise RuntimeContractError("embedding input cannot be empty")
        if len(ids) > self.limits.max_context_tokens:
            raise RuntimeContractError("embedding input exceeds context budget")
        if any(
            not _is_int(token_id)
            or token_id < 0
            or token_id >= len(self.model.itos)
            for token_id in ids
        ):
            raise RuntimeContractError("invalid embedding token id")
        rows = self.model._encode(ids)
        return tuple(tuple(float(value) for value in row) for row in rows)

    def embed_text(self, text: str) -> tuple[tuple[float, ...], ...]:
        return self.embed_ids(self.encode(text))

    def _prepare_prompt(
        self,
        prompt: str,
        sampling: SamplingConfig,
    ) -> tuple[TokenSequence, tuple[int, ...], bool]:
        sequence = self.tokenizer.encode(prompt)
        ids = sequence.token_ids
        truncated = False
        if len(ids) > self.limits.max_context_tokens:
            if sampling.context_policy == "reject":
                raise RuntimeContractError("prompt exceeds context budget")
            ids = ids[-self.limits.max_context_tokens :]
            truncated = True
        return sequence, tuple(ids), truncated

    def forward(self, prompt: str, *, context_policy: str = "reject") -> ForwardPass:
        sampling = SamplingConfig(max_new_tokens=0, context_policy=context_policy)
        full_sequence, ids, _ = self._prepare_prompt(prompt, sampling)
        with self._lock:
            hidden, _caches = self.model._forward(ids)
            last = hidden[-1] if hidden else [0.0] * self.model.dim
            logits = self.model._unembed(last)
            probs = softmax(logits)
        return ForwardPass(
            full_sequence,
            tuple(float(value) for value in last),
            tuple(float(value) for value in logits),
            tuple(float(value) for value in probs),
            self.model_digest,
        )

    def next_token_logits(
        self,
        prompt: str,
        *,
        context_policy: str = "reject",
    ) -> tuple[float, ...]:
        return self.forward(prompt, context_policy=context_policy).logits

    def _sampling_digest(self, sampling: SamplingConfig) -> str:
        return _digest(sampling.to_dict())

    def _request_digest(self, prompt: str, sampling: SamplingConfig) -> str:
        return _digest({
            "schema": RUNTIME_SCHEMA,
            "model_digest": self.model_digest,
            "tokenizer_digest": self.tokenizer.digest,
            "prompt_digest": _text_digest(prompt),
            "sampling": sampling.to_dict(),
        })

    def _validate_sampling_against_runtime(self, sampling: SamplingConfig) -> None:
        if sampling.max_new_tokens > self.limits.max_output_tokens:
            raise RuntimeContractError("generation exceeds runtime output budget")
        if sampling.top_k > len(self.model.itos):
            raise RuntimeContractError("top_k exceeds vocabulary size")
        if any(token_id >= len(self.model.itos) for token_id in sampling.stop_token_ids):
            raise RuntimeContractError("stop token id exceeds vocabulary")
        self._admit_memory(use_cache=sampling.use_cache)

    def _decode_generated(
        self,
        token_ids: Sequence[int],
    ) -> tuple[tuple[str, ...], str]:
        tokens = tuple(self.model.itos[token_id] for token_id in token_ids)
        return tokens, self.tokenizer.decode_ids(token_ids)

    def generate(
        self,
        prompt: str,
        config: SamplingConfig | None = None,
    ) -> GenerationResult:
        sampling = config or SamplingConfig()
        if not isinstance(sampling, SamplingConfig):
            raise RuntimeContractError("SamplingConfig required")
        if not isinstance(prompt, str):
            raise RuntimeContractError("prompt must be a string")
        self._validate_sampling_against_runtime(sampling)
        request_digest = self._request_digest(prompt, sampling)
        trace_start = self._event_sequence

        with self._lock:
            full_sequence, prompt_ids, truncated = self._prepare_prompt(prompt, sampling)
            self._emit(
                "request_admitted",
                request_digest,
                prompt_tokens=len(prompt_ids),
                max_new_tokens=sampling.max_new_tokens,
                context_truncated=truncated,
            )
            if sampling.use_cache:
                self._metrics["cache_requests"] += 1

            # Python KV state is exact for host weights. TorchAccel owns its own
            # resident execution state; mixing its weights with the host cache
            # could read stale values, so cache use is disabled on accelerator
            # rather than silently blending execution backends.
            cache_used = bool(
                sampling.use_cache
                and getattr(self.model, "_accel", None) is None
            )
            cache = (
                KVCache(self.model.n_layers, self.limits.max_context_tokens)
                if cache_used
                else None
            )
            if cache_used:
                self._metrics["cache_uses"] += 1

            rng = random.Random(int(sampling.seed) & 0xFFFFFFFF)
            history = list(prompt_ids)
            generated: list[int] = []
            self._emit(
                "prefill_complete",
                request_digest,
                cache_used=cache_used,
                device=self.actual_device,
            )

            for ordinal in range(sampling.max_new_tokens):
                window = history[-self.limits.max_context_tokens :]
                logits = self.model._logits_window(window, cache)
                token_id = int(sample_logits(
                    logits,
                    rng,
                    temperature=float(sampling.temperature),
                    top_k=sampling.top_k,
                    top_p=float(sampling.top_p),
                ))
                if token_id < 0 or token_id >= len(self.model.itos):
                    raise RuntimeContractError("sampler emitted invalid token id")
                generated.append(token_id)
                history.append(token_id)
                if token_id in sampling.stop_token_ids:
                    self._emit(
                        "stop_token",
                        request_digest,
                        ordinal=ordinal,
                        token_id=token_id,
                    )
                    break

            generated_ids = tuple(generated)
            generated_tokens, text = self._decode_generated(generated_ids)
            output_digest = _text_digest(text)
            self._metrics["requests"] += 1
            self._metrics["prompt_tokens"] += len(prompt_ids)
            self._metrics["generated_tokens"] += len(generated_ids)
            if truncated:
                self._metrics["context_truncations"] += 1
            self._emit(
                "generation_complete",
                request_digest,
                generated_tokens=len(generated_ids),
                cache_used=cache_used,
                output_digest=output_digest,
            )
            trace = self._trace_since(trace_start, request_digest)
            trace_digest = _digest([event.to_dict() for event in trace])
            receipt = InferenceReceipt(
                request_digest=request_digest,
                model_digest=self.model_digest,
                tokenizer_digest=self.tokenizer.digest,
                prompt_digest=_text_digest(prompt),
                prompt_tokens=len(prompt_ids),
                generated_token_ids=generated_ids,
                output_digest=output_digest,
                sampling_digest=self._sampling_digest(sampling),
                cache_requested=sampling.use_cache,
                cache_used=cache_used,
                context_truncated=truncated,
                actual_device=self.actual_device,
                trace_digest=trace_digest,
            )
            return GenerationResult(
                full_sequence,
                generated_ids,
                generated_tokens,
                text,
                receipt,
            )

    def generate_batch(
        self,
        requests: Iterable[InferenceRequest],
    ) -> tuple[GenerationResult, ...]:
        batch = tuple(requests)
        if not batch or len(batch) > self.limits.max_batch_size:
            raise RuntimeContractError("batch size out of bounds")
        ids = [request.request_id for request in batch]
        if len(set(ids)) != len(ids):
            raise RuntimeContractError("duplicate request_id in batch")
        aggregate = 0
        for request in batch:
            prompt_tokens = len(self.encode(request.prompt))
            aggregate += prompt_tokens + request.sampling.max_new_tokens
        if aggregate > self.limits.max_batch_tokens:
            raise RuntimeContractError("batch token budget exceeded")
        # Stable serial execution today; the contract can later be backed by a
        # vectorized scheduler without changing receipts or caller semantics.
        return tuple(
            self.generate(request.prompt, request.sampling)
            for request in batch
        )

    def replay(
        self,
        prompt: str,
        sampling: SamplingConfig,
        expected: InferenceReceipt,
    ) -> GenerationResult:
        if not isinstance(expected, InferenceReceipt):
            raise RuntimeContractError("InferenceReceipt required")
        if expected.model_digest != self.model_digest:
            raise RuntimeContractError("replay model identity mismatch")
        if expected.tokenizer_digest != self.tokenizer.digest:
            raise RuntimeContractError("replay tokenizer identity mismatch")
        if expected.prompt_digest != _text_digest(prompt):
            raise RuntimeContractError("replay prompt digest mismatch")
        if expected.sampling_digest != self._sampling_digest(sampling):
            raise RuntimeContractError("replay sampling mismatch")
        result = self.generate(prompt, sampling)
        if result.receipt.semantic_digest != expected.semantic_digest:
            raise RuntimeContractError("deterministic replay mismatch")
        with self._lock:
            self._metrics["replays"] += 1
            self._emit(
                "replay_verified",
                expected.request_digest,
                semantic_digest=expected.semantic_digest,
            )
        return result

    def checkpoint(self) -> Mapping[str, Any]:
        with self._lock:
            model = self._semantic_model_snapshot()
            tokenizer = self.tokenizer.state.to_dict()
            body: dict[str, Any] = {
                "schema": CHECKPOINT_SCHEMA,
                "runtime_schema": RUNTIME_SCHEMA,
                "model": model,
                "tokenizer": tokenizer,
                "limits": self.limits.to_dict(),
                "model_digest": self.model_digest,
                "tokenizer_digest": self.tokenizer.digest,
            }
            body["checkpoint_digest"] = _digest(body)
            return body

    def checkpoint_digest(self) -> str:
        return str(self.checkpoint()["checkpoint_digest"])

    @classmethod
    def restore(
        cls,
        checkpoint: Mapping[str, Any],
        *,
        device: str | None = None,
        allow_device_fallback: bool = True,
    ) -> "NativeLLMRuntime":
        if not isinstance(checkpoint, Mapping):
            raise RuntimeContractError("checkpoint mapping required")
        raw = dict(checkpoint)
        if raw.get("schema") not in {
            CHECKPOINT_SCHEMA,
            "skeleton.ai.native-llm.v1",
        }:
            raise RuntimeContractError("unsupported checkpoint schema")

        # Initial branch cut compatibility.
        if raw.get("schema") == "skeleton.ai.native-llm.v1":
            model_blob = raw.get("model")
            if not isinstance(model_blob, Mapping):
                raise RuntimeContractError("legacy checkpoint model missing")
            model = TinyTransformer.from_snapshot(dict(model_blob))
            runtime = cls(
                model,
                device=device,
                allow_device_fallback=allow_device_fallback,
            )
            expected = raw.get("digest")
            if expected is not None and runtime.model_digest != expected:
                legacy = sha256(json.dumps(
                    dict(model_blob),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()).hexdigest()
                if legacy != expected:
                    raise RuntimeContractError(
                        "legacy checkpoint integrity failure"
                    )
            return runtime

        expected_fields = {
            "schema",
            "runtime_schema",
            "model",
            "tokenizer",
            "limits",
            "model_digest",
            "tokenizer_digest",
            "checkpoint_digest",
        }
        if set(raw) != expected_fields:
            raise RuntimeContractError("checkpoint fields drifted")
        if raw.get("runtime_schema") != RUNTIME_SCHEMA:
            raise RuntimeContractError("checkpoint runtime schema mismatch")
        checkpoint_digest = _require_digest(
            raw.pop("checkpoint_digest", None),
            "checkpoint_digest",
        )
        if _digest(raw) != checkpoint_digest:
            raise RuntimeContractError("checkpoint integrity failure")

        model_blob = raw.get("model")
        tokenizer_blob = raw.get("tokenizer")
        limits_blob = raw.get("limits")
        if (
            not isinstance(model_blob, Mapping)
            or not isinstance(tokenizer_blob, Mapping)
            or not isinstance(limits_blob, Mapping)
        ):
            raise RuntimeContractError("checkpoint components missing")

        expected_limit_fields = set(RuntimeLimits.__dataclass_fields__)
        if set(limits_blob) != expected_limit_fields:
            raise RuntimeContractError("checkpoint runtime limits drifted")
        if set(tokenizer_blob) != {"schema", "vocabulary", "bpe"}:
            raise RuntimeContractError("checkpoint tokenizer fields drifted")
        limits = RuntimeLimits(**dict(limits_blob))
        numeric_count = cls._count_numeric_payload(model_blob)
        if numeric_count * 8 > limits.max_model_bytes:
            raise RuntimeContractError(
                "checkpoint model exceeds memory budget"
            )
        model = TinyTransformer.from_snapshot(dict(model_blob))

        bpe_blob = tokenizer_blob.get("bpe")
        if bpe_blob is not None:
            if not isinstance(bpe_blob, Mapping):
                raise RuntimeContractError("checkpoint BPE state malformed")
            from skeleton.cortex.bpe import BytePairEncoder
            model.bpe = BytePairEncoder.from_snapshot(dict(bpe_blob))

        runtime = cls(model, limits=limits)
        state = TokenizerState(
            tokenizer_blob.get("schema"),
            tuple(tokenizer_blob.get("vocabulary") or ()),
            None if bpe_blob is None else dict(bpe_blob),
        )
        if state.digest != runtime.tokenizer.digest:
            raise RuntimeContractError(
                "checkpoint tokenizer state mismatch"
            )
        if (
            _require_digest(raw.get("model_digest"), "model_digest")
            != runtime.model_digest
        ):
            raise RuntimeContractError(
                "checkpoint model identity mismatch"
            )
        if (
            _require_digest(
                raw.get("tokenizer_digest"),
                "tokenizer_digest",
            )
            != runtime.tokenizer.digest
        ):
            raise RuntimeContractError(
                "checkpoint tokenizer identity mismatch"
            )
        if device is not None:
            runtime.bind_device(
                device,
                allow_fallback=allow_device_fallback,
            )
        runtime._emit(
            "checkpoint_restored",
            None,
            checkpoint_digest=checkpoint_digest,
        )
        return runtime


__all__ = [
    "CHECKPOINT_SCHEMA",
    "ForwardPass",
    "GenerationConfig",
    "GenerationResult",
    "InferenceReceipt",
    "InferenceRequest",
    "NativeLLMRuntime",
    "RUNTIME_SCHEMA",
    "RuntimeContractError",
    "RuntimeEvent",
    "RuntimeLimits",
    "RuntimeMemoryReport",
    "SamplingConfig",
]
