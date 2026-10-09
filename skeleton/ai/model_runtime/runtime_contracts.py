"""Typed contracts for the native FLGB-02 language-model runtime."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .flgb_model_runtime import digest_json, require_id

MAX_CONTEXT = 1_000_000
MAX_NEW_TOKENS = 1_000_000
MAX_TOTAL_TOKENS = 2_000_000
MAX_MODEL_BYTES = 2**40
MAX_KV_BYTES = 2**40
MAX_BATCH_SIZE = 4096
MAX_BATCH_TOKENS = 4_000_000
MAX_CHECKPOINT_BYTES = 256_000_000
RUNTIME_SCHEMA = "skeleton.ai.native-llm-runtime.v2"
REPLAY_SCHEMA = "skeleton.ai.native-llm-replay.v1"


class RuntimeContractError(ValueError):
    """Fail-closed native LLM runtime contract violation."""


class ReplayMismatch(RuntimeContractError):
    """Deterministic replay did not reproduce its admitted receipt."""


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def positive_int(value: Any, name: str, upper: int) -> int:
    if not is_int(value) or not 1 <= value <= upper:
        raise RuntimeContractError(f"invalid {name}")
    return int(value)


def nonnegative_int(value: Any, name: str, upper: int) -> int:
    if not is_int(value) or not 0 <= value <= upper:
        raise RuntimeContractError(f"invalid {name}")
    return int(value)


def runtime_id(value: Any, name: str) -> str:
    try:
        return require_id(value, name)
    except ValueError as exc:
        raise RuntimeContractError(f"invalid {name}") from exc


def runtime_digest(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise RuntimeContractError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class RuntimeLimits:
    max_context: int
    max_new_tokens: int
    max_total_tokens: int
    max_model_bytes: int = MAX_MODEL_BYTES
    max_kv_bytes: int = MAX_KV_BYTES
    max_batch_size: int = 64
    max_batch_tokens: int = 262_144
    max_checkpoint_bytes: int = MAX_CHECKPOINT_BYTES

    def __post_init__(self) -> None:
        positive_int(self.max_context, "max_context", MAX_CONTEXT)
        positive_int(self.max_new_tokens, "max_new_tokens", MAX_NEW_TOKENS)
        positive_int(self.max_total_tokens, "max_total_tokens", MAX_TOTAL_TOKENS)
        positive_int(self.max_model_bytes, "max_model_bytes", MAX_MODEL_BYTES)
        positive_int(self.max_kv_bytes, "max_kv_bytes", MAX_KV_BYTES)
        positive_int(self.max_batch_size, "max_batch_size", MAX_BATCH_SIZE)
        positive_int(self.max_batch_tokens, "max_batch_tokens", MAX_BATCH_TOKENS)
        positive_int(self.max_checkpoint_bytes, "max_checkpoint_bytes", MAX_CHECKPOINT_BYTES)
        if self.max_total_tokens < self.max_context:
            raise RuntimeContractError("total-token budget cannot be below context budget")
        if self.max_batch_tokens < self.max_context:
            raise RuntimeContractError("batch token budget cannot be below context budget")

    @classmethod
    def for_model(cls, model: Any) -> "RuntimeLimits":
        ctx = positive_int(getattr(model, "ctx", None), "model context", MAX_CONTEXT)
        return cls(
            max_context=ctx,
            max_new_tokens=max(1, ctx),
            max_total_tokens=min(MAX_TOTAL_TOKENS, max(2, ctx * 2)),
            max_batch_tokens=min(MAX_BATCH_TOKENS, max(262_144, ctx * 64)),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "max_context": self.max_context,
            "max_new_tokens": self.max_new_tokens,
            "max_total_tokens": self.max_total_tokens,
            "max_model_bytes": self.max_model_bytes,
            "max_kv_bytes": self.max_kv_bytes,
            "max_batch_size": self.max_batch_size,
            "max_batch_tokens": self.max_batch_tokens,
            "max_checkpoint_bytes": self.max_checkpoint_bytes,
        }


@dataclass(frozen=True)
class DevicePolicy:
    requested: str = "cpu"
    allow_fallback: bool = True
    kv_dtype: str = "fp32"
    kv_limit_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.requested not in {"cpu", "auto", "cuda", "gpu", "mps", "torch", "torch-cpu"}:
            raise RuntimeContractError("unsupported device request")
        if not isinstance(self.allow_fallback, bool):
            raise RuntimeContractError("allow_fallback must be boolean")
        if self.kv_dtype not in {"fp32", "fp16", "bf16"}:
            raise RuntimeContractError("unsupported KV cache precision")
        if self.kv_limit_bytes is not None and (
            not is_int(self.kv_limit_bytes) or self.kv_limit_bytes <= 0
            or self.kv_limit_bytes > MAX_KV_BYTES
        ):
            raise RuntimeContractError("KV cache byte ceiling out of bounds")

    def to_dict(self) -> dict[str, Any]:
        # Preserve historic checkpoint/device-policy digests by omitting
        # new cache options unless explicitly selected by the operator.
        result: dict[str, Any] = {
            "requested": self.requested, "allow_fallback": self.allow_fallback,
        }
        if self.kv_dtype != "fp32":
            result["kv_dtype"] = self.kv_dtype
        if self.kv_limit_bytes is not None:
            result["kv_limit_bytes"] = self.kv_limit_bytes
        return result


@dataclass(frozen=True)
class DeviceReceipt:
    requested: str
    actual: str
    resident: bool
    degraded: bool
    kv_dtype: str = "fp32"
    kv_limit_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical device receipt fields for runtime identity binding."""
        result: dict[str, Any] = {
            "requested": self.requested,
            "actual": self.actual,
            "resident": self.resident,
            "degraded": self.degraded,
        }
        if self.kv_dtype != "fp32":
            result["kv_dtype"] = self.kv_dtype
        if self.kv_limit_bytes is not None:
            result["kv_limit_bytes"] = self.kv_limit_bytes
        return result

    @property
    def digest(self) -> str:
        return digest_json(self.to_dict())


@dataclass(frozen=True)
class RuntimeArchitecture:
    vocab_size: int
    dim: int
    context: int
    heads: int
    layers: int
    feed_forward: int
    norm: str
    ffn_kind: str
    positional: str = "learned-position-embedding+rope-attention"

    def __post_init__(self) -> None:
        positive_int(self.vocab_size, "vocab_size", 2**31 - 1)
        positive_int(self.dim, "dim", 1_000_000)
        positive_int(self.context, "context", MAX_CONTEXT)
        positive_int(self.heads, "heads", self.dim)
        positive_int(self.layers, "layers", 65_536)
        nonnegative_int(self.feed_forward, "feed_forward", 16_000_000)
        if self.dim % self.heads:
            raise RuntimeContractError("runtime dimension must be divisible by heads")
        if self.norm not in {"ln", "rms"}:
            raise RuntimeContractError("unsupported runtime norm")
        if self.ffn_kind not in {"gelu", "swiglu"}:
            raise RuntimeContractError("unsupported runtime FFN")
        runtime_id(self.positional, "positional")

    @property
    def digest(self) -> str:
        return digest_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "vocab_size": self.vocab_size,
            "dim": self.dim,
            "context": self.context,
            "heads": self.heads,
            "layers": self.layers,
            "feed_forward": self.feed_forward,
            "norm": self.norm,
            "ffn_kind": self.ffn_kind,
            "positional": self.positional,
        }


@dataclass(frozen=True)
class GenerationConfig:
    max_new_tokens: int = 32
    seed: int = 0
    temperature: float = 1.0
    top_k: int = 0
    top_p: float = 1.0
    use_cache: bool = True
    stop_token_ids: tuple[int, ...] = ()

    def validate(self, *, limits: RuntimeLimits, vocab_size: int) -> "GenerationConfig":
        nonnegative_int(self.max_new_tokens, "max_new_tokens", limits.max_new_tokens)
        if not is_int(self.seed):
            raise RuntimeContractError("seed must be an integer")
        if (
            not isinstance(self.temperature, (int, float))
            or isinstance(self.temperature, bool)
            or not math.isfinite(float(self.temperature))
            or not 0.0 <= float(self.temperature) <= 100.0
        ):
            raise RuntimeContractError("temperature outside supported range")
        if not is_int(self.top_k) or not 0 <= self.top_k <= vocab_size:
            raise RuntimeContractError("top_k outside vocabulary")
        if (
            not isinstance(self.top_p, (int, float))
            or isinstance(self.top_p, bool)
            or not math.isfinite(float(self.top_p))
            or not 0.0 < float(self.top_p) <= 1.0
        ):
            raise RuntimeContractError("top_p outside supported range")
        if not isinstance(self.use_cache, bool):
            raise RuntimeContractError("use_cache must be boolean")
        seen: set[int] = set()
        for token_id in self.stop_token_ids:
            if not is_int(token_id) or not 0 <= token_id < vocab_size or token_id in seen:
                raise RuntimeContractError("invalid stop token id")
            seen.add(token_id)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_new_tokens": self.max_new_tokens,
            "seed": self.seed,
            "temperature": float(self.temperature),
            "top_k": self.top_k,
            "top_p": float(self.top_p),
            "use_cache": self.use_cache,
            "stop_token_ids": list(self.stop_token_ids),
        }


@dataclass(frozen=True)
class RuntimeUsage:
    prompt_tokens: int
    generated_tokens: int
    total_tokens: int
    model_bytes: int
    kv_peak_bytes: int
    cache_resets: int

    def __post_init__(self) -> None:
        nonnegative_int(self.prompt_tokens, "prompt_tokens", MAX_TOTAL_TOKENS)
        nonnegative_int(self.generated_tokens, "generated_tokens", MAX_NEW_TOKENS)
        nonnegative_int(self.total_tokens, "total_tokens", MAX_TOTAL_TOKENS)
        positive_int(self.model_bytes, "model_bytes", MAX_MODEL_BYTES)
        nonnegative_int(self.kv_peak_bytes, "kv_peak_bytes", MAX_KV_BYTES)
        nonnegative_int(self.cache_resets, "cache_resets", MAX_TOTAL_TOKENS)
        if self.total_tokens != self.prompt_tokens + self.generated_tokens:
            raise RuntimeContractError("runtime usage token accounting mismatch")

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "generated_tokens": self.generated_tokens,
            "total_tokens": self.total_tokens,
            "model_bytes": self.model_bytes,
            "kv_peak_bytes": self.kv_peak_bytes,
            "cache_resets": self.cache_resets,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.to_dict())


@dataclass(frozen=True)
class RuntimeEvent:
    sequence: int
    kind: str
    token_id: int | None = None
    text_delta: str = ""
    cache_tokens: int = 0
    detail_digest: str | None = None

    def __post_init__(self) -> None:
        if not is_int(self.sequence) or self.sequence < 0:
            raise RuntimeContractError("invalid event sequence")
        if self.kind not in {"admitted", "prompt", "token", "stopped", "completed"}:
            raise RuntimeContractError("invalid runtime event kind")
        if self.token_id is not None and (not is_int(self.token_id) or self.token_id < 0):
            raise RuntimeContractError("invalid event token id")
        if not isinstance(self.text_delta, str):
            raise RuntimeContractError("text_delta must be a string")
        if not is_int(self.cache_tokens) or self.cache_tokens < 0:
            raise RuntimeContractError("invalid cache token count")
        if self.detail_digest is not None and (
            len(self.detail_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.detail_digest)
        ):
            raise RuntimeContractError("invalid event detail digest")


@dataclass(frozen=True)
class ReplayReceipt:
    model_digest: str
    tokenizer_digest: str
    architecture_digest: str
    request_digest: str
    output_digest: str
    config_digest: str
    device_digest: str
    seed: int
    schema: str = REPLAY_SCHEMA

    def __post_init__(self) -> None:
        for name in (
            "model_digest",
            "tokenizer_digest",
            "architecture_digest",
            "request_digest",
            "output_digest",
            "config_digest",
            "device_digest",
        ):
            runtime_digest(getattr(self, name), name)
        if not is_int(self.seed):
            raise RuntimeContractError("replay seed must be an integer")
        if self.schema != REPLAY_SCHEMA:
            raise RuntimeContractError("unsupported replay receipt schema")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "model_digest": self.model_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "architecture_digest": self.architecture_digest,
            "request_digest": self.request_digest,
            "output_digest": self.output_digest,
            "config_digest": self.config_digest,
            "device_digest": self.device_digest,
            "seed": self.seed,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.to_dict())


@dataclass(frozen=True)
class BatchGenerationRequest:
    request_id: str
    prompt: str
    config: GenerationConfig = GenerationConfig()

    def __post_init__(self) -> None:
        runtime_id(self.request_id, "request_id")
        if not isinstance(self.prompt, str):
            raise RuntimeContractError("batch prompt must be a string")
        if not isinstance(self.config, GenerationConfig):
            raise RuntimeContractError("GenerationConfig required")


__all__ = [
    "BatchGenerationRequest",
    "DevicePolicy",
    "DeviceReceipt",
    "GenerationConfig",
    "MAX_CHECKPOINT_BYTES",
    "REPLAY_SCHEMA",
    "RUNTIME_SCHEMA",
    "ReplayMismatch",
    "ReplayReceipt",
    "RuntimeArchitecture",
    "RuntimeContractError",
    "RuntimeEvent",
    "RuntimeLimits",
    "RuntimeUsage",
    "is_int",
    "nonnegative_int",
    "positive_int",
    "runtime_digest",
    "runtime_id",
]
