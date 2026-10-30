"""Concrete offline llama.cpp CLI backend for Skeleton local inference.

This backend turns the provider-independent LocalModelBackend contract into a
real process boundary for operator-owned GGUF/open-weight models. It never
uses a shell, never places prompt text in argv, binds both executable and model
artifact identities, bounds process output, observes cooperative cancellation,
and strips hosted-provider/proxy credentials from the child environment.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import signal
import struct
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from skeleton.skills.tool_contract import (
    ToolContractError,
    validate_json_schema,
    validate_json_value,
)

from .kv_placement import observe_native_kv_placement
from .local import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalToolCall,
)

_COMPLETION_EOG_TRAILERS = (" [end of text]\n\n\n", " [end of text]\n")
# These are the two existing operator-provisioned profiles, not a general
# Jinja interpreter. Keep their manifest spelling stable for installed receipts.
COMPLETION_CHAT_FLAGS = (
    "--conversation", "--single-turn", "--simple-io", "--no-perf",
    "--no-escape", "--color", "off", "--jinja", "--reasoning", "off",
)
CODING_COMPLETION_CHAT_TEMPLATE = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\\n' + message['content'] + '<|im_end|>\\n' }}"
    "{% endfor %}{% if add_generation_prompt %}"
    "{{ '<|im_start|>assistant\\n' }}"
    "{% endif %}"
)
QWEN3_COMPLETION_CHAT_TEMPLATE = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\\n' + message['content'] + '<|im_end|>\\n' }}"
    "{% endfor %}{% if add_generation_prompt %}"
    "{{ '<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n' }}"
    "{% endif %}"
)
_CHATML_CONTENT_DELIMITERS = ("<|im_start|>", "<|im_end|>", "<|endoftext|>")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_PROVIDER_SECRET_NAMES = {
    "OPENAI" + "_API_KEY",
    "ANTHROPIC" + "_API_KEY",
    "XAI" + "_API_KEY",
    "GOOGLE" + "_API_KEY",
    "AZURE_OPENAI" + "_API_KEY",
}
_PROXY_NAMES = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
}
_INHERITED_ENV_ALLOWLIST = {
    "PATH",
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "CUDA_VISIBLE_DEVICES",
    "ROCR_VISIBLE_DEVICES",
    "HIP_VISIBLE_DEVICES",
    "OMP_NUM_THREADS",
    "GGML_CUDA_ENABLE_UNIFIED_MEMORY",
}
_MANAGED_LONG_FLAGS = {
    "--model",
    "--prompt",
    "--file",
    "--binary-file",
    "--n-predict",
    "--seed",
    "--temp",
    "--ctx-size",
    "--threads",
    "--batch-size",
    "--gpu-layers",
    "--kv-offload",
    "--no-kv-offload",
    "--cache-type-k",
    "--cache-type-v",
    "--grammar",
    "--grammar-file",
    "--json-schema",
    "--json-schema-file",
}
_MANAGED_SHORT_FLAGS = (
    "-m",
    "-p",
    "-f",
    "-n",
    "-c",
    "-t",
    "-b",
    "-bf",
    "-ngl",
    "-kvo",
    "-nkvo",
    "-ctk",
    "-ctv",
    "-j",
    "-jf",
    "-s",
)
_REMOTE_ACQUISITION_FLAGS = {
    "--hf-repo",
    "--hf-file",
    "--model-url",
    "--url",
    "--download",
    "--hf-repo-v",
    "--hf-token",
    "--rpc",
    "--rpc-server",
    "--host",
    "--port",
}
_REMOTE_ACQUISITION_SHORT_FLAGS = ("-hf", "-hfr", "-hff", "-hfv", "-hft")


class LlamaCppRuntimeError(RuntimeError):
    """The local llama.cpp process boundary failed closed."""


@dataclass(frozen=True, slots=True)
class GgufHeader:
    """Small immutable admission record from the fixed GGUF file header."""

    version: int
    tensor_count: int
    metadata_count: int

    def __post_init__(self) -> None:
        if self.version not in {2, 3}:
            raise ValueError("supported GGUF version must be 2 or 3")
        if self.tensor_count <= 0:
            raise ValueError("GGUF tensor_count must be positive")
        if self.metadata_count < 0:
            raise ValueError("GGUF metadata_count must be non-negative")


@dataclass(frozen=True, slots=True)
class GgufServingMetadata:
    """Bounded serving geometry read from the already identity-bound GGUF."""

    architecture: str | None = None
    context_length: int | None = None
    embedding_length: int | None = None
    block_count: int | None = None
    head_count: int | None = None
    head_count_kv: int | None = None
    key_length: int | None = None
    value_length: int | None = None

    def __post_init__(self) -> None:
        if self.architecture is not None and (
            not isinstance(self.architecture, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.architecture)
        ):
            raise ValueError("GGUF architecture must be a bounded identifier")
        for name in (
            "context_length", "embedding_length", "block_count", "head_count",
            "head_count_kv", "key_length", "value_length",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or not 0 < value <= 2_147_483_647):
                raise ValueError("GGUF serving dimensions must be bounded positive integers")

    def as_dict(self) -> dict[str, Any]:
        return {
            "architecture": self.architecture,
            "context_length": self.context_length,
            "embedding_length": self.embedding_length,
            "block_count": self.block_count,
            "head_count": self.head_count,
            "head_count_kv": self.head_count_kv,
            "key_length": self.key_length,
            "value_length": self.value_length,
        }

    @property
    def kv_bytes_per_token_upper_bound(self) -> int | None:
        heads = self.head_count
        kv_heads = self.head_count_kv or heads
        layers = self.block_count
        key = self.key_length
        value = self.value_length
        if key is None and self.embedding_length and heads and self.embedding_length % heads == 0:
            key = self.embedding_length // heads
        if value is None:
            value = key
        if not all(type(item) is int and 0 < item <= 65536 for item in (layers, heads, kv_heads, key, value)):
            return None
        if kv_heads > heads or heads % kv_heads:
            return None
        # f32 is the largest regular llama.cpp KV element. Quantized caches
        # reduce this logical bound; allocator/scratch headroom is separate.
        return layers * kv_heads * (key + value) * 4


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    path: str
    sha256: str
    size_bytes: int
    mtime_ns: int
    inode: int | None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("artifact path must be non-empty")
        if not _HEX64.fullmatch(self.sha256):
            raise ValueError("artifact sha256 must be lowercase hex")
        if self.size_bytes <= 0:
            raise ValueError("artifact must be non-empty")


@dataclass(frozen=True, slots=True)
class LlamaCppConfig:
    executable: str
    model_path: str
    model_id: str | None = None
    timeout_seconds: float = 120.0
    max_output_bytes: int = 4 * 1024 * 1024
    max_stderr_bytes: int = 512 * 1024
    context_size: int | None = None
    threads: int | None = None
    batch_size: int | None = None
    gpu_layers: int | None = None
    kv_cache_location: str = "backend"
    kv_cache_type_k: str | None = None
    kv_cache_type_v: str | None = None
    temperature: float = 0.0
    extra_args: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    reject_model_symlink: bool = True
    rehash_artifacts_each_run: bool = False
    output_framing: str = "raw"
    runtime_scratch_bytes: int = 512 * 1024 * 1024
    kv_bytes_per_token: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.executable, str) or not self.executable.strip():
            raise ValueError("executable must be non-empty")
        if not isinstance(self.model_path, str) or not self.model_path.strip():
            raise ValueError("model_path must be non-empty")
        if self.model_id is not None and not self.model_id.strip():
            raise ValueError("model_id must be non-empty when provided")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(float(self.timeout_seconds))
            or not 0.05 <= float(self.timeout_seconds) <= 86400
        ):
            raise ValueError("timeout_seconds must be finite and in [0.05, 86400]")
        for name, value, lower, upper in (
            ("max_output_bytes", self.max_output_bytes, 1024, 64 * 1024 * 1024),
            ("max_stderr_bytes", self.max_stderr_bytes, 1024, 16 * 1024 * 1024),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise ValueError(f"{name} must be in [{lower}, {upper}]")
        for name, value, lower, upper in (
            ("context_size", self.context_size, 128, 1_048_576),
            ("threads", self.threads, 1, 4096),
            ("batch_size", self.batch_size, 1, 1_048_576),
            ("gpu_layers", self.gpu_layers, 0, 1_048_576),
            ("kv_bytes_per_token", self.kv_bytes_per_token, 1, 1024 * 1024 * 1024),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper
            ):
                raise ValueError(f"{name} must be in [{lower}, {upper}]")
        if type(self.runtime_scratch_bytes) is not int or not 0 <= self.runtime_scratch_bytes <= 64 * 1024**3:
            raise ValueError("runtime_scratch_bytes must be an integer in [0, 64 GiB]")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(float(self.temperature))
            or not 0 <= float(self.temperature) <= 10
        ):
            raise ValueError("temperature must be finite and in [0, 10]")
        if not isinstance(self.output_framing, str) or self.output_framing not in {
            "raw",
            "llama_completion_eog",
        }:
            raise ValueError("output_framing must be raw or llama_completion_eog")
        if type(self.kv_cache_location) is not str or self.kv_cache_location not in {
            "backend", "host",
        }:
            raise ValueError("kv_cache_location must be backend or host")
        supported_kv_types = {"f16", "q8_0", "q4_0"}
        for name in ("kv_cache_type_k", "kv_cache_type_v"):
            value = getattr(self, name)
            if value is not None and (
                type(value) is not str or value not in supported_kv_types
            ):
                raise ValueError(
                    f"{name} requires explicit f16, q8_0 or q4_0"
                )
        normalized_args: list[str] = []
        for item in self.extra_args:
            if not isinstance(item, str) or not item:
                raise ValueError("extra_args must contain non-empty strings")
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in item):
                raise ValueError("extra_args may not contain control characters")
            option = item.split("=", 1)[0] if item.startswith("--") else item
            managed = option in _MANAGED_LONG_FLAGS
            if not item.startswith("--"):
                managed = managed or any(
                    item == flag
                    or (item.startswith(flag) and len(item) > len(flag) and item[len(flag)] not in {"-", "_"})
                    for flag in _MANAGED_SHORT_FLAGS
                )
            if managed:
                raise ValueError(f"extra_args may not override managed flag {item}")
            remote = option in _REMOTE_ACQUISITION_FLAGS
            if not item.startswith("--"):
                remote = remote or any(
                    item == flag or item.startswith(flag + "=") for flag in _REMOTE_ACQUISITION_SHORT_FLAGS
                )
            if remote:
                raise ValueError(
                    f"extra_args may not enable remote model acquisition or network access {item}"
                )
            normalized_args.append(item)
        object.__setattr__(self, "extra_args", tuple(normalized_args))

        normalized_env: dict[str, str] = {}
        for key, value in dict(self.environment).items():
            if not isinstance(key, str) or not _ENV_KEY.fullmatch(key):
                raise ValueError(f"invalid environment key {key!r}")
            if key in _PROVIDER_SECRET_NAMES or key in _PROXY_NAMES or key.startswith("LLAMA_ARG_"):
                raise ValueError(f"forbidden environment key {key}")
            if not isinstance(value, str) or "\x00" in value:
                raise ValueError(f"invalid environment value for {key}")
            normalized_env[key] = value
        object.__setattr__(self, "environment", normalized_env)


@dataclass(frozen=True, slots=True)
class ConsumerHardwareBudget:
    """Explicit RAM and KV budget for an offline quantized GGUF deployment.

    kv_bytes_per_token MUST be supplied from the specific model/selected KV
    representation. GGUF file size alone cannot determine attention memory.
    ram_bytes is the operator's *available* machine/cgroup memory, not a
    machine-class guess, and GPU offloading remains an independent backend
    concern. This is conservative admission planning, not an OOM guarantee.
    """

    ram_bytes: int
    physical_cpu_cores: int
    kv_bytes_per_token: int
    target_context_tokens: int = 4096
    reserve_bytes: int = 512 * 1024 * 1024
    runtime_scratch_bytes: int = 512 * 1024 * 1024
    max_decode_threads: int = 16
    prefill_batch_tokens: int = 256

    def __post_init__(self) -> None:
        for name in (
            "ram_bytes",
            "physical_cpu_cores",
            "kv_bytes_per_token",
            "target_context_tokens",
            "max_decode_threads",
            "prefill_batch_tokens",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("reserve_bytes", "runtime_scratch_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative")
        if not 128 <= self.target_context_tokens <= 1_048_576:
            raise ValueError("target_context_tokens outside llama.cpp bounds")


@dataclass(frozen=True, slots=True)
class ConsumerLlamaPlan:
    """Auditable configuration chosen without claiming to measure performance."""

    configuration: LlamaCppConfig
    model_bytes: int
    reserved_ram_bytes: int
    reserved_kv_bytes: int
    estimated_total_bytes: int
    available_ram_bytes: int
    context_clamped: bool


def estimate_gqa_kv_bytes_per_token(
    *,
    layers: int,
    query_heads: int,
    kv_heads: int,
    key_head_dim: int,
    value_head_dim: int,
    key_bytes_per_element: int = 2,
    value_bytes_per_element: int = 2,
) -> int:
    """Exact logical K/V tensor bytes per token from known model geometry.

    Supports multi-head (kv_heads=query_heads), grouped-query and multi-query
    attention. It deliberately excludes allocator padding, paging overhead and
    backend scratch; the consumer RAM planner reserves those separately.
    It is not correct to infer KV geometry from GGUF file size alone.
    """
    fields = {
        "layers": layers,
        "query_heads": query_heads,
        "kv_heads": kv_heads,
        "key_head_dim": key_head_dim,
        "value_head_dim": value_head_dim,
        "key_bytes_per_element": key_bytes_per_element,
        "value_bytes_per_element": value_bytes_per_element,
    }
    for name, value in fields.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 65536:
            raise ValueError(f"{name} must be a bounded positive integer")
    if kv_heads > query_heads or query_heads % kv_heads:
        raise ValueError("query head count must be divisible by KV head count")
    if key_bytes_per_element > 8 or value_bytes_per_element > 8:
        raise ValueError("KV element width must be <= 8 bytes")
    return (
        layers * kv_heads * (key_head_dim * key_bytes_per_element + value_head_dim * value_bytes_per_element)
    )


def detect_consumer_hardware_budget(
    *,
    kv_bytes_per_token: int,
    target_context_tokens: int = 4096,
    available_ram_bytes: int | None = None,
    physical_cpu_cores: int | None = None,
) -> ConsumerHardwareBudget:
    """Conservatively probe an offline host; fail rather than invent capacity.

    psutil, when installed, works on Windows, macOS and Linux. On Linux
    /proc/meminfo and /proc/cpuinfo allow a standard-library-only fallback.
    Cgroup v2 memory and CPU quotas and process affinity tighten the budget.
    Optional explicit overrides support constrained and headless deployments.
    """

    def positive(value: object, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise LlamaCppRuntimeError(f"invalid detected {name}")
        return value

    memory = available_ram_bytes
    cores = physical_cpu_cores
    if memory is None or cores is None:
        try:
            import psutil  # type: ignore[import-not-found]  # optional host probe
        except ImportError:
            psutil = None
        if psutil is not None:
            if memory is None:
                memory = int(psutil.virtual_memory().available)
            if cores is None:
                detected = psutil.cpu_count(logical=False)
                cores = int(detected) if detected else None
    if memory is None:
        try:
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                if line.startswith("MemAvailable:"):
                    memory = int(line.split()[1]) * 1024
                    break
        except (OSError, ValueError, IndexError):
            pass
    if cores is None:
        try:
            pairs = set()
            physical = logical_core = None
            for line in Path("/proc/cpuinfo").read_text(encoding="ascii").splitlines() + [""]:
                if not line.strip():
                    if physical is not None and logical_core is not None:
                        pairs.add((physical, logical_core))
                    physical = logical_core = None
                elif line.startswith("physical id"):
                    physical = line.split(":", 1)[1].strip()
                elif line.startswith("core id"):
                    logical_core = line.split(":", 1)[1].strip()
            if pairs:
                cores = len(pairs)
        except (OSError, ValueError, IndexError):
            pass
    if memory is None or cores is None:
        raise LlamaCppRuntimeError(
            "cannot determine available RAM and physical cores; provide explicit values"
        )
    memory = positive(memory, "available RAM")
    cores = positive(cores, "physical CPU count")

    # Linux containers may see the entire host's RAM from psutil or /proc.
    # The effective budget cannot exceed unallocated cgroup allowance.
    cgroup = Path("/sys/fs/cgroup")
    try:
        max_text = (cgroup / "memory.max").read_text(encoding="ascii").strip()
        if max_text != "max":
            mem_limit = int(max_text)
            mem_current = int((cgroup / "memory.current").read_text(encoding="ascii"))
            if mem_limit <= 0 or mem_current < 0:
                raise LlamaCppRuntimeError("invalid cgroup memory accounting")
            memory = min(memory, max(0, mem_limit - mem_current))
    except (OSError, ValueError):
        pass
    # Container CPU quotas can be smaller than visible physical core count.
    try:
        if hasattr(os, "sched_getaffinity"):
            cores = min(cores, len(os.sched_getaffinity(0)))
    except OSError:
        pass
    try:
        quota_text, period_text = (cgroup / "cpu.max").read_text(encoding="ascii").split()
        if quota_text != "max":
            quota, period = int(quota_text), int(period_text)
            if quota <= 0 or period <= 0:
                raise LlamaCppRuntimeError("invalid cgroup CPU quota")
            cores = min(cores, max(1, (quota + period - 1) // period))
    except (OSError, ValueError):
        pass
    return ConsumerHardwareBudget(
        ram_bytes=positive(memory, "effective available RAM"),
        physical_cpu_cores=positive(cores, "effective CPU cores"),
        kv_bytes_per_token=kv_bytes_per_token,
        target_context_tokens=target_context_tokens,
    )


def plan_consumer_llama_cpp(
    config: LlamaCppConfig,
    budget: ConsumerHardwareBudget,
    *,
    model_bytes: int,
) -> ConsumerLlamaPlan:
    """Choose context, batch and CPU threads before launching llama.cpp.

    Reserves 20% RAM or the explicit floor for the OS, then charges full GGUF
    bytes, configured scratch headroom and model-specific KV requirements.
    Does not fabricate a GPU layer split, infer quantization from file size,
    or promise that a backend will actually fit (other buffers may exist).
    """
    if not isinstance(config, LlamaCppConfig):
        raise TypeError("config must be LlamaCppConfig")
    if not isinstance(budget, ConsumerHardwareBudget):
        raise TypeError("budget must be ConsumerHardwareBudget")
    if isinstance(model_bytes, bool) or not isinstance(model_bytes, int) or model_bytes <= 0:
        raise ValueError("model_bytes must be positive")
    reserved = max(budget.reserve_bytes, budget.ram_bytes // 5)
    fixed = reserved + budget.runtime_scratch_bytes + model_bytes
    available_for_kv = budget.ram_bytes - fixed
    minimum_kv = budget.kv_bytes_per_token * 128
    if available_for_kv < minimum_kv:
        raise LlamaCppRuntimeError("GGUF weights, KV cache and runtime headroom exceed consumer RAM budget")
    requested = config.context_size or budget.target_context_tokens
    possible = min(requested, available_for_kv // budget.kv_bytes_per_token)
    context = (possible // 128) * 128
    if context < 128:
        raise LlamaCppRuntimeError("consumer RAM budget cannot support minimum context")
    threads = min(
        config.threads or budget.physical_cpu_cores, budget.physical_cpu_cores, budget.max_decode_threads
    )
    batch = min(config.batch_size or budget.prefill_batch_tokens, budget.prefill_batch_tokens, context)
    chosen = replace(
        config, context_size=context, threads=threads, batch_size=batch,
        runtime_scratch_bytes=budget.runtime_scratch_bytes,
        kv_bytes_per_token=budget.kv_bytes_per_token,
    )
    kv_total = context * budget.kv_bytes_per_token
    return ConsumerLlamaPlan(
        configuration=chosen,
        model_bytes=model_bytes,
        reserved_ram_bytes=reserved,
        reserved_kv_bytes=kv_total,
        estimated_total_bytes=fixed + kv_total,
        available_ram_bytes=budget.ram_bytes,
        context_clamped=context < requested,
    )


def _sha256_file(path: Path, *, interrupt: Callable[[], None] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if interrupt is not None:
                interrupt()
            digest.update(chunk)
    return digest.hexdigest()


def inspect_gguf(path: Path) -> GgufHeader:
    """Validate the fixed GGUF header without trusting extension or filename."""

    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError as exc:
        raise LlamaCppRuntimeError(f"cannot read GGUF model header: {path}") from exc
    if len(header) != 24:
        raise LlamaCppRuntimeError("model artifact is too small to be GGUF")
    magic, version, tensor_count, metadata_count = struct.unpack("<4sIQQ", header)
    if magic != b"GGUF":
        raise LlamaCppRuntimeError("model artifact does not contain GGUF magic")
    if version not in {2, 3}:
        raise LlamaCppRuntimeError(f"unsupported GGUF version: {version}")
    if tensor_count <= 0:
        raise LlamaCppRuntimeError("GGUF model declares zero tensors")
    return GgufHeader(
        version=version,
        tensor_count=tensor_count,
        metadata_count=metadata_count,
    )


def _serving_metadata(path: Path, header: GgufHeader) -> GgufServingMetadata:
    """Read selected scalar metadata; never materialize tokenizer vocabularies."""
    if header.metadata_count > 65_536:
        raise LlamaCppRuntimeError("GGUF metadata entry count exceeds serving bound")
    formats = {
        0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i",
        6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d",
    }
    suffixes = {
        "context_length", "embedding_length", "block_count", "attention.head_count",
        "attention.head_count_kv", "attention.key_length", "attention.value_length",
    }
    selected: dict[str, Any] = {}
    seen: set[str] = set()
    try:
        with path.open("rb") as handle:
            limit = min(path.stat().st_size, 24 + 64 * 1024 * 1024)
            handle.seek(24)

            def take(count: int) -> bytes:
                if count < 0 or handle.tell() + count > limit:
                    raise LlamaCppRuntimeError("GGUF metadata exceeds bounded file region")
                data = handle.read(count)
                if len(data) != count:
                    raise LlamaCppRuntimeError("truncated GGUF metadata")
                return data

            def skip(count: int) -> None:
                if count < 0 or handle.tell() + count > limit:
                    raise LlamaCppRuntimeError("GGUF metadata exceeds bounded file region")
                handle.seek(count, os.SEEK_CUR)

            def string(*, retain: bool, maximum: int = 4096) -> str | None:
                length = struct.unpack("<Q", take(8))[0]
                if not retain:
                    skip(length)
                    return None
                if length > maximum:
                    raise LlamaCppRuntimeError("GGUF serving metadata string exceeds bound")
                return take(length).decode("utf-8", errors="strict")

            def value(kind: int, *, retain: bool) -> Any:
                fmt = formats.get(kind)
                if fmt is not None:
                    raw = take(struct.calcsize(fmt))
                    if kind == 7 and raw not in {b"\x00", b"\x01"}:
                        raise LlamaCppRuntimeError("invalid GGUF boolean metadata")
                    return struct.unpack(fmt, raw)[0] if retain else None
                if kind == 8:
                    return string(retain=retain)
                if kind != 9:
                    raise LlamaCppRuntimeError("unsupported GGUF metadata value type")
                item_type, count = struct.unpack("<IQ", take(12))
                if count > 2_097_152 or item_type == 9:
                    raise LlamaCppRuntimeError("GGUF metadata array exceeds serving bound")
                if retain:
                    raise LlamaCppRuntimeError("GGUF serving geometry must use scalar metadata")
                if item_type == 8:
                    for _ in range(count):
                        string(retain=False)
                elif item_type in formats:
                    skip(count * struct.calcsize(formats[item_type]))
                else:
                    raise LlamaCppRuntimeError("unsupported GGUF metadata array type")
                return None

            for _ in range(header.metadata_count):
                key = string(retain=True, maximum=1024)
                if not key or key in seen:
                    raise LlamaCppRuntimeError("empty or duplicate GGUF metadata key")
                seen.add(key)
                retain = key == "general.architecture" or any(key.endswith("." + suffix) for suffix in suffixes)
                kind = struct.unpack("<I", take(4))[0]
                observed = value(kind, retain=retain)
                if retain:
                    if len(selected) >= 512:
                        raise LlamaCppRuntimeError("GGUF serving metadata key count exceeds bound")
                    selected[key] = observed
    except (OSError, UnicodeError, struct.error) as exc:
        raise LlamaCppRuntimeError("cannot read bounded GGUF serving metadata") from exc
    architecture = selected.get("general.architecture")
    if architecture is not None and (
        not isinstance(architecture, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", architecture)
    ):
        raise LlamaCppRuntimeError("GGUF architecture metadata is invalid")

    def integer(suffix: str) -> int | None:
        raw = selected.get(f"{architecture}.{suffix}") if architecture is not None else None
        if raw is not None and (type(raw) is not int or not 0 < raw <= 2_147_483_647):
            raise LlamaCppRuntimeError("GGUF serving geometry is not a bounded positive integer")
        return raw

    return GgufServingMetadata(
        architecture=architecture,
        context_length=integer("context_length"),
        embedding_length=integer("embedding_length"),
        block_count=integer("block_count"),
        head_count=integer("attention.head_count"),
        head_count_kv=integer("attention.head_count_kv"),
        key_length=integer("attention.key_length"),
        value_length=integer("attention.value_length"),
    )


def _identity(path_value: str, *, executable: bool, reject_symlink: bool) -> ArtifactIdentity:
    raw = Path(path_value).expanduser()
    if executable and not raw.is_absolute():
        resolved_command = shutil.which(path_value)
        if resolved_command is None:
            raise FileNotFoundError(f"local runtime executable not found: {path_value}")
        raw = Path(resolved_command)
    lexical = Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"local artifact not found: {raw}") from exc
    if reject_symlink and lexical != resolved:
        raise LlamaCppRuntimeError(f"artifact symlinked path component rejected: {raw}")
    if not resolved.is_file():
        raise LlamaCppRuntimeError(f"local artifact is not a regular file: {resolved}")
    if executable and not os.access(resolved, os.X_OK):
        raise PermissionError(f"local runtime is not executable: {resolved}")
    before = resolved.stat()
    digest = _sha256_file(resolved)
    after = resolved.stat()
    before_tuple = (before.st_size, before.st_mtime_ns, getattr(before, "st_ino", None))
    after_tuple = (after.st_size, after.st_mtime_ns, getattr(after, "st_ino", None))
    if before_tuple != after_tuple:
        raise LlamaCppRuntimeError(f"artifact changed while hashing: {resolved}")
    return ArtifactIdentity(
        path=str(resolved),
        sha256=digest,
        size_bytes=after.st_size,
        mtime_ns=after.st_mtime_ns,
        inode=getattr(after, "st_ino", None),
    )


def _stat_matches(identity: ArtifactIdentity) -> bool:
    try:
        stat = Path(identity.path).stat()
    except OSError:
        return False
    return (
        stat.st_size == identity.size_bytes
        and stat.st_mtime_ns == identity.mtime_ns
        and getattr(stat, "st_ino", None) == identity.inode
    )


def _approx_tokens(text: str) -> int:
    return len(_TOKEN.findall(text))


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def llama_cpp_prompt_tokens_upper_bound(request: LocalInferenceRequest) -> int:
    """Bound known completion profiles without asserting which one is active.

    This sizes bytes only. Actual admission still validates control markers and
    artifact identity; custom CLI profiles retain their own runtime behavior.
    """
    if not isinstance(request, LocalInferenceRequest):
        raise TypeError("request must be LocalInferenceRequest")
    profiles = (None, "skeleton.chatml.coding.v1", "skeleton.chatml.qwen3-closed-think.v1")
    return max(
        len(LlamaCppModel._render_prompt_for_profile(request, profile, validate_content=False).encode("utf-8")) + 1
        for profile in profiles
    )


class LlamaCppModel:
    """Run an exact, identity-bound local model through llama.cpp's CLI."""

    model_family = "gguf_open_weight"
    protocol_capabilities = ("text-generation", "tool-calls", "structured-output")
    tokenizer_kind = "utf8_bytes_upper_bound"

    def count_input_tokens(self, request: LocalInferenceRequest) -> int:
        # The CLI owns its GGUF tokenizer. UTF-8 bytes conservatively admit
        # byte-fallback tokenizers without pretending a word regex is exact.
        return len(self._render_prompt(request).encode("utf-8")) + 1

    def check_readiness(self) -> None:
        """Cheap stat-based readiness; dispatch still owns full SHA admission."""
        if (
            self.model_id != self._admitted_model_id
            or not _stat_matches(self._runtime)
            or not _stat_matches(self._model)
            or not os.access(self._runtime.path, os.R_OK | os.X_OK)
            or not os.access(self._model.path, os.R_OK)
            or (self.config.reject_model_symlink and Path(self._model.path).is_symlink())
        ):
            raise LlamaCppRuntimeError("activated local runtime/model file changed or is unavailable")

    def __init__(self, config: LlamaCppConfig) -> None:
        if not isinstance(config, LlamaCppConfig):
            raise TypeError("config must be LlamaCppConfig")
        self.config = config
        self._runtime = _identity(config.executable, executable=True, reject_symlink=False)
        self._model = _identity(
            config.model_path,
            executable=False,
            reject_symlink=config.reject_model_symlink,
        )
        self._gguf_header = inspect_gguf(Path(self._model.path))
        self._serving_metadata = _serving_metadata(Path(self._model.path), self._gguf_header)
        self._process_lock = threading.Lock()
        self._active_processes: set[int] = set()
        self._draining_processes: set[int] = set()
        self._spawning_processes = 0
        self._processes_started = 0
        self._inference_admitted = False
        self._resource_profile_bound = False
        self._resource_preflight: Callable[[], None] | None = None
        self._resource_preflight_bound = False
        self._resource_preflight_checks = 0
        self._last_kv_observation: dict[str, Any] | None = None
        self._processes_exited = 0
        self._termination_requests = 0
        if not _stat_matches(self._model):
            raise LlamaCppRuntimeError("GGUF artifact changed while reading serving metadata")
        if self._serving_metadata.architecture in {
            "clip", "bert", "nomic-bert", "nomic-bert-moe", "jina-bert-v2", "t5encoder", "whisper",
        }:
            raise LlamaCppRuntimeError("GGUF architecture is not a text-generation model")
        self.model_id = (
            config.model_id.strip()
            if config.model_id is not None
            else f"llama.cpp:{Path(self._model.path).stem}:{self._model.sha256[:12]}"
        )
        self._admitted_model_id = self.model_id

    def activate_prelaunch_resource_profile(
        self, profile: LlamaCppConfig,
    ) -> None:
        """Bind measured CPU/Metal flags before any inference has started.

        Device memory allocation, actual KV residency and synchronization
        remain owned by llama.cpp. This cannot escalate source, network,
        model identity, security or output authority, and may not retune
        an executing or previously activated process.
        """
        if not isinstance(profile, LlamaCppConfig):
            raise TypeError("verified LlamaCppConfig required")
        immutable_fields = (
            "executable", "model_path", "model_id", "timeout_seconds",
            "max_output_bytes", "max_stderr_bytes", "context_size",
            "temperature", "extra_args", "environment",
            "reject_model_symlink", "rehash_artifacts_each_run",
            "output_framing", "runtime_scratch_bytes",
            "kv_bytes_per_token", "kv_cache_type_k", "kv_cache_type_v",
        )
        if any(getattr(profile, field) != getattr(self.config, field)
               for field in immutable_fields):
            raise LlamaCppRuntimeError(
                "resource retuning cannot change model, safety or context identity"
            )
        if profile.kv_cache_location != self.config.kv_cache_location:
            if not (self.config.kv_cache_location == "backend"
                    and profile.kv_cache_location == "host"):
                raise LlamaCppRuntimeError(
                    "resource adaptation cannot activate GPU KV offloading"
                )
        for field in ("gpu_layers", "threads", "batch_size"):
            original = getattr(self.config, field)
            proposed = getattr(profile, field)
            if original is not None and proposed is not None and proposed > original:
                raise LlamaCppRuntimeError(
                    "adaptive profile may not exceed operator request"
                )
            if field == "gpu_layers" and original is None and proposed not in (None, 0):
                raise LlamaCppRuntimeError(
                    "adaptive profile cannot silently activate GPU offload"
                )
        with self._process_lock:
            if getattr(self, "_resource_profile_bound", False):
                raise LlamaCppRuntimeError(
                    "adaptive runtime profile was already bound"
                )
            if (getattr(self, "_inference_admitted", False)
                    or self._processes_started or self._active_processes
                    or self._draining_processes or self._spawning_processes):
                raise LlamaCppRuntimeError(
                    "runtime profile cannot change after inference admission"
                )
            self._assert_artifacts_stable()
            self.config = profile
            self._resource_profile_bound = True

    def install_prelaunch_resource_guard(self, guard: Callable[[], None]) -> None:
        """Install one trusted resource-preflight callback before inference.

        The callback may only reject a request: it does not change model,
        execution flags, backend identity or GPU allocations.
        """
        if not callable(guard):
            raise TypeError("prelaunch resource guard must be callable")
        with self._process_lock:
            if (getattr(self, "_resource_preflight_bound", False)
                    or getattr(self, "_inference_admitted", False)
                    or self._processes_started or self._spawning_processes):
                raise LlamaCppRuntimeError(
                    "resource guard cannot be installed after admission"
                )
            self._resource_preflight = guard
            self._resource_preflight_bound = True

    @property
    def model_digest(self) -> str:
        return self._model.sha256

    @property
    def runtime_digest(self) -> str:
        return self._runtime.sha256

    @property
    def execution_profile_digest(self) -> str:
        """Bind decoding/resource policy without changing executable identity."""
        profile = {
            "schema": "skeleton.llama-cpp.execution-profile.v1",
            "runtime": self.runtime_digest,
            "model": self.model_digest,
            "model_id": self._admitted_model_id,
            "context_size": self.config.context_size,
            "threads": self.config.threads,
            "batch_size": self.config.batch_size,
            "gpu_layers": self.config.gpu_layers,
            "kv_cache_location": self.config.kv_cache_location,
            "kv_cache_type_k": self.config.kv_cache_type_k,
            "kv_cache_type_v": self.config.kv_cache_type_v,
            "temperature": float(self.config.temperature),
            "extra_args": list(self.config.extra_args),
            "output_framing": self.config.output_framing,
            "output_framing_suffixes": (
                list(_COMPLETION_EOG_TRAILERS)
                if self.config.output_framing == "llama_completion_eog"
                else []
            ),
            "timeout_seconds": float(self.config.timeout_seconds),
            "max_output_bytes": self.config.max_output_bytes,
            "max_stderr_bytes": self.config.max_stderr_bytes,
            "environment_digest": _digest(self._effective_environment()),
            "serving_metadata": self._serving_metadata.as_dict(),
            "runtime_scratch_bytes": self.config.runtime_scratch_bytes,
            "kv_bytes_per_token": self.config.kv_bytes_per_token,
            "seed_policy": "uint32_mod_4294967295_without_random_sentinel",
        }
        native_chat_profile = self._native_chat_profile()
        if native_chat_profile is not None:
            # A corrected role renderer must not reuse a generation cached
            # under the old single-user-blob conversation transport.
            profile["prompt_format"] = native_chat_profile
        return _digest(profile)

    def _effective_context(self) -> int:
        configured = self.config.context_size
        if configured is None:
            raise LlamaCppRuntimeError("GGUF serving requires an explicit context_size")
        trained = self._serving_metadata.context_length
        return configured if trained is None else min(configured, trained)

    def generation_limits(self) -> dict[str, Any]:
        """Publish the same bounded context passed to the exact CLI process."""
        context = self._effective_context()
        return {
            "context_window": context,
            "max_output_tokens": min(8192, max(1, context // 2)),
            "max_total_tokens": context,
            "shared_context": True,
            "tokenizer": self.tokenizer_kind,
            "max_output_utf8_bytes": min(self.config.max_output_bytes, 4 * 1024 * 1024),
            "limits_source": "activated_local_backend",
        }

    def execution_snapshot(self) -> dict[str, Any]:
        with self._process_lock:
            return {
                "kind": "llama_cpp_cli",
                "active_processes": len(self._active_processes),
                "draining_processes": len(self._draining_processes),
                "spawning_processes": self._spawning_processes,
                "processes_started": self._processes_started,
                "processes_exited": self._processes_exited,
                "termination_requests": self._termination_requests,
                "trained_context_known": self._serving_metadata.context_length is not None,
                "trained_context_tokens": self._serving_metadata.context_length,
                "kv_estimate_available": bool(
                    self.config.kv_bytes_per_token or self._serving_metadata.kv_bytes_per_token_upper_bound
                ),
                "memory_estimate_source": self.memory_estimate_source,
                "resource_preflight_bound": self._resource_preflight_bound,
                "resource_preflight_checks": self._resource_preflight_checks,
            }

    @property
    def memory_estimate_source(self) -> str:
        known_kv = self.config.kv_bytes_per_token or self._serving_metadata.kv_bytes_per_token_upper_bound
        return "gguf_process_weights_scratch_and_kv" if known_kv is not None else "gguf_process_weights_scratch_kv_unknown"

    def estimate_memory_bytes(self, request: LocalInferenceRequest) -> int:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        # Each CLI invocation is a separate process. Charge full GGUF pages,
        # scratch and context KV conservatively, including GPU-offloaded
        # models; this is host admission, not measured VRAM or shared-page use.
        context = self._effective_context()
        kv = self.config.kv_bytes_per_token or self._serving_metadata.kv_bytes_per_token_upper_bound or 0
        return self._model.size_bytes + self.config.runtime_scratch_bytes + context * kv

    @property
    def model_artifact(self) -> ArtifactIdentity:
        return self._model

    @property
    def runtime_artifact(self) -> ArtifactIdentity:
        return self._runtime

    @property
    def gguf_header(self) -> GgufHeader:
        return self._gguf_header

    @property
    def serving_metadata(self) -> GgufServingMetadata:
        return self._serving_metadata

    def _assert_artifacts_stable(self, *, interrupt: Callable[[], None] | None = None) -> None:
        if self.model_id != self._admitted_model_id:
            raise LlamaCppRuntimeError("activated local model identifier changed")
        for label, identity in (("runtime", self._runtime), ("model", self._model)):
            if interrupt is not None:
                interrupt()
            if not _stat_matches(identity):
                raise LlamaCppRuntimeError(f"{label} artifact identity changed")
            if self.config.rehash_artifacts_each_run:
                observed = _sha256_file(Path(identity.path), interrupt=interrupt)
                if observed != identity.sha256:
                    raise LlamaCppRuntimeError(f"{label} artifact digest changed")
                if not _stat_matches(identity):
                    raise LlamaCppRuntimeError(f"{label} artifact changed during admission")
        observed_header = inspect_gguf(Path(self._model.path))
        if observed_header != self._gguf_header:
            raise LlamaCppRuntimeError("GGUF fixed header changed")

    def assert_identity(self) -> None:
        """Admit cached answers against the same artifact policy as execution."""
        self._assert_artifacts_stable()

    def _native_chat_profile(self) -> str | None:
        if self.config.output_framing != "llama_completion_eog":
            return None
        for template, profile in (
            (CODING_COMPLETION_CHAT_TEMPLATE, "skeleton.chatml.coding.v1"),
            (QWEN3_COMPLETION_CHAT_TEMPLATE, "skeleton.chatml.qwen3-closed-think.v1"),
        ):
            if self.config.extra_args == (*COMPLETION_CHAT_FLAGS, "--chat-template", template):
                return profile
        return None

    def _render_prompt(self, request: LocalInferenceRequest) -> str:
        return self._render_prompt_for_profile(request, self._native_chat_profile())

    @classmethod
    def _render_prompt_for_profile(
        cls, request: LocalInferenceRequest, profile: str | None, *, validate_content: bool = True,
    ) -> str:
        if profile is None:
            # Generic local/reference/custom deployments retain their exact
            # historical text protocol and operator-selected CLI behavior.
            return request.rendered_input + cls._prompt_protocol(request)

        protocol = cls._prompt_protocol(request, include_schema=True)
        messages: list[tuple[str, str]] = []
        if request.instructions.strip() or protocol:
            messages.append(("system", request.instructions + protocol))
        messages.extend(request.history)
        messages.append(("user", request.prompt))
        for _, content in messages:
            if validate_content and any(marker in content for marker in _CHATML_CONTENT_DELIMITERS):
                raise LlamaCppRuntimeError("local message contains a reserved ChatML control delimiter")
        rendered = "".join(
            "<|im_start|>" + role + "\n" + content + "<|im_end|>\n"
            for role, content in messages
        )
        rendered += "<|im_start|>assistant\n"
        if profile == "skeleton.chatml.qwen3-closed-think.v1":
            rendered += "<think>\n\n</think>\n\n"
        return rendered

    @classmethod
    def _prompt_protocol(cls, request: LocalInferenceRequest, *, include_schema: bool = False) -> str:
        if not request.tools:
            if request.structured_output_schema is None:
                return ""
            contract = (
                "\n\n[Skeleton local structured-output protocol]\n"
                + "Output exactly one JSON object matching the supplied schema. "
                + "Do not include markdown fences or prose outside the JSON object."
            )
            if include_schema:
                contract += "\nRequired JSON schema: " + _stable_json(
                    cls._normalized_structured_output_schema(request)
                )
            return contract
        allowed: list[dict[str, Any]] = []
        seen_tool_ids: set[str] = set()
        for item in request.tools:
            tool_id = str(item.get("tool_id", "")).strip()
            if not tool_id:
                raise LlamaCppRuntimeError("local tool schema missing tool_id")
            if tool_id in seen_tool_ids:
                raise LlamaCppRuntimeError("duplicate local tool_id")
            seen_tool_ids.add(tool_id)
            allowed.append(
                {
                    "tool_id": tool_id,
                    "description": str(item.get("description", "")),
                    "input_schema": item.get("input_schema", {}),
                }
            )
        contract = (
            "\n\n[Skeleton local tool protocol]\n"
            "When a tool is required, output exactly one JSON object and no prose: "
            '{"skeleton_local_response":1,"tool_calls":'
            '[{"call_id":"stable-id","tool_id":"allowed-id","arguments":{}}]}.\n'
            "Never invent a tool_id. Otherwise answer normally.\n"
            + (
                "If final structured output is requested, place it under "
                "structured_output and match the supplied schema.\n"
                if request.structured_output_schema is not None
                else ""
            )
            + "Allowed tools: "
            + _stable_json(allowed)
        )
        if request.tool_choice in {"required", "specific"}:
            contract += "\nA tool call is required for this turn; do not return a prose-only answer."
        if request.tool_choice == "specific":
            contract += "\nRequired tool_id: " + str(request.specific_tool_id)
        if include_schema and request.structured_output_schema is not None:
            contract += "\nRequired final JSON schema: " + _stable_json(
                cls._normalized_structured_output_schema(request)
            )
        return contract

    @staticmethod
    def _normalized_structured_output_schema(
        request: LocalInferenceRequest,
    ) -> dict[str, Any] | None:
        if request.structured_output_schema is None:
            return None
        try:
            schema = validate_json_schema(request.structured_output_schema)
        except ToolContractError as exc:
            raise LlamaCppRuntimeError(f"invalid structured output schema: {exc}") from exc
        if schema.get("type") not in {None, "object"}:
            raise LlamaCppRuntimeError("local structured output schema must describe an object")
        return schema

    def _tool_response_schema(self, request: LocalInferenceRequest) -> dict[str, Any]:
        allowed_tool_ids = sorted(
            {
                str(item.get("tool_id", "")).strip()
                for item in request.tools
                if str(item.get("tool_id", "")).strip()
            }
        )
        if not allowed_tool_ids:
            raise LlamaCppRuntimeError("tool response schema requires at least one declared tool_id")
        structured_schema = self._normalized_structured_output_schema(request)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["skeleton_local_response"],
            "properties": {
                "skeleton_local_response": {"const": 1},
                "text": {"type": "string", "minLength": 1},
                "structured_output": ({"type": "object"} if structured_schema is None else structured_schema),
                "tool_calls": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["call_id", "tool_id", "arguments"],
                        "properties": {
                            "call_id": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 256,
                            },
                            "tool_id": {
                                "type": "string",
                                "enum": allowed_tool_ids,
                            },
                            "arguments": {"type": "object"},
                        },
                    },
                },
            },
            "anyOf": [
                {"required": ["text"]},
                {"required": ["structured_output"]},
                {"required": ["tool_calls"]},
            ],
        }
        if request.tool_choice in {"required", "specific"}:
            schema["required"].append("tool_calls")
            schema["anyOf"] = [{"required": ["tool_calls"]}]
        return schema

    def _generation_schema(
        self,
        request: LocalInferenceRequest,
    ) -> dict[str, Any] | None:
        if request.tools:
            return self._tool_response_schema(request)
        return self._normalized_structured_output_schema(request)

    def _command(
        self,
        prompt_file: Path,
        request: LocalInferenceRequest,
        *,
        schema_file: Path | None = None,
    ) -> list[str]:
        command = [
            self._runtime.path,
            "-m",
            self._model.path,
            "--binary-file" if self._native_chat_profile() is not None else "-f",
            str(prompt_file),
            "-n",
            str(request.max_output_tokens),
            "--seed",
            str(request.seed % 0xFFFFFFFF),
            "--temp",
            format(float(self.config.temperature), ".12g"),
            "--no-display-prompt",
        ]
        command.extend(("-c", str(self._effective_context())))
        if self.config.threads is not None:
            command.extend(("-t", str(self.config.threads)))
        if self.config.batch_size is not None:
            command.extend(("-b", str(self.config.batch_size)))
        if self.config.gpu_layers is not None:
            command.extend(("-ngl", str(self.config.gpu_layers)))
        if self.config.kv_cache_location == "host":
            command.append("--no-kv-offload")
        if self.config.kv_cache_type_k is not None:
            command.extend(("--cache-type-k", self.config.kv_cache_type_k))
        if self.config.kv_cache_type_v is not None:
            command.extend(("--cache-type-v", self.config.kv_cache_type_v))
        if schema_file is not None:
            command.extend(("--json-schema-file", str(schema_file)))
        if self._native_chat_profile() is None:
            command.extend(self.config.extra_args)
        else:
            # -f strips one trailing newline in the pinned completion CLI;
            # binary-file preserves the exact assistant generation prefix.
            # Conversation mode would wrap the entire file as one user turn.
            command.extend(("--no-conversation", "--simple-io", "--no-perf", "--no-escape", "--color", "off"))
        return command

    def _effective_environment(self) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key in _INHERITED_ENV_ALLOWLIST
            and key not in _PROVIDER_SECRET_NAMES
            and key not in _PROXY_NAMES
        }
        env.update(dict(self.config.environment))
        for key in _PROVIDER_SECRET_NAMES | _PROXY_NAMES:
            env.pop(key, None)
        return env

    def _child_environment(self, temp_dir: Path) -> dict[str, str]:
        env = self._effective_environment()
        env["HOME"] = str(temp_dir)
        env["TMPDIR"] = str(temp_dir)
        env["SKELETON_LOCAL_MODEL_NETWORK"] = "disabled"
        for key in _PROVIDER_SECRET_NAMES | _PROXY_NAMES:
            env.pop(key, None)
        return env

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except (OSError, ProcessLookupError):
            pass
        try:
            process.wait(timeout=1.0)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (OSError, ProcessLookupError):
            pass
        # Killing requests termination; it does not prove that the OS worker
        # has gone. Keep ownership until wait actually reaps the model process,
        # including an uninterruptible process or a temporarily failed signal.
        while process.poll() is None:
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                try:
                    if os.name != "nt":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except (OSError, ProcessLookupError):
                    pass

    @staticmethod
    def _load_protocol_json(text: str) -> Any:
        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise LlamaCppRuntimeError("duplicate JSON key in local model output")
                result[key] = value
            return result

        def reject_constant(value: str) -> None:
            raise LlamaCppRuntimeError("non-finite JSON constant in local model output")

        try:
            return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
        except (json.JSONDecodeError, RecursionError) as exc:
            categories = {
                "Extra data": "extra_data",
                "Expecting value": "expected_value",
                "Unterminated string starting at": "unterminated_string",
                "Expecting property name enclosed in double quotes": "expected_property",
                "Expecting ',' delimiter": "expected_comma",
                "Expecting ':' delimiter": "expected_colon",
                "Invalid \\escape": "invalid_escape",
                "Invalid control character at": "invalid_control",
            }
            prefix_class = (
                "object"
                if text.startswith("{")
                else "array" if text.startswith("[") else "empty" if not text else "other"
            )
            logging.getLogger(__name__).warning(
                "Local JSON failure: exception=%s category=%s pos=%s line=%s column=%s "
                "chars=%d prefix=%s declared_eog_tail=%s",
                type(exc).__name__,
                "depth" if isinstance(exc, RecursionError) else categories.get(exc.msg, "other_decoder"),
                getattr(exc, "pos", None),
                getattr(exc, "lineno", None),
                getattr(exc, "colno", None),
                len(text),
                prefix_class,
                text.endswith(" [end of text]"),
            )
            raise LlamaCppRuntimeError("local model output is not valid bounded JSON") from exc

    def _parse_output(
        self,
        raw: str,
        request: LocalInferenceRequest,
    ) -> tuple[str | None, tuple[LocalToolCall, ...], Mapping[str, Any] | None, str]:
        text = raw.strip()
        if not text:
            raise LlamaCppRuntimeError("local runtime produced empty output")
        allowed_tool_ids = {
            str(item.get("tool_id", "")).strip()
            for item in request.tools
            if str(item.get("tool_id", "")).strip()
        }
        if text.startswith("{"):
            try:
                payload = self._load_protocol_json(text)
            except LlamaCppRuntimeError:
                if request.tools or request.structured_output_schema is not None:
                    raise
                payload = None
            if isinstance(payload, dict) and "skeleton_local_response" in payload:
                version = payload["skeleton_local_response"]
                if type(version) is not int or version != 1:
                    raise LlamaCppRuntimeError("unsupported local response protocol version")
                if set(payload) - {"skeleton_local_response", "text", "tool_calls", "structured_output"}:
                    raise LlamaCppRuntimeError("unsupported field in local response envelope")
                raw_calls = payload.get("tool_calls", [])
                if not isinstance(raw_calls, list):
                    raise LlamaCppRuntimeError("tool_calls envelope must be a list")
                calls: list[LocalToolCall] = []
                for raw_call in raw_calls:
                    if not isinstance(raw_call, dict):
                        raise LlamaCppRuntimeError("local tool call must be an object")
                    if set(raw_call) != {"call_id", "tool_id", "arguments"}:
                        raise LlamaCppRuntimeError("invalid local tool call fields")
                    if not isinstance(raw_call["call_id"], str) or not isinstance(raw_call["tool_id"], str):
                        raise LlamaCppRuntimeError("local tool identifiers must be strings")
                    call_id = raw_call["call_id"].strip()
                    tool_id = raw_call["tool_id"].strip()
                    arguments = raw_call.get("arguments", {})
                    if not call_id:
                        raise LlamaCppRuntimeError("local tool call missing call_id")
                    if tool_id not in allowed_tool_ids:
                        raise LlamaCppRuntimeError(f"local model requested undeclared tool_id {tool_id!r}")
                    if not isinstance(arguments, dict):
                        raise LlamaCppRuntimeError("local tool arguments must be an object")
                    calls.append(LocalToolCall(call_id=call_id, tool_id=tool_id, arguments=arguments))
                payload_text = payload.get("text")
                if payload_text is not None and not isinstance(payload_text, str):
                    raise LlamaCppRuntimeError("local response text must be text or null")
                if isinstance(payload_text, str) and not payload_text.strip():
                    raise LlamaCppRuntimeError("local response text cannot be empty")
                structured = payload.get("structured_output")
                if structured is not None and not isinstance(structured, dict):
                    raise LlamaCppRuntimeError("structured_output must be an object")
                if structured is not None and request.structured_output_schema is not None:
                    try:
                        validate_json_value(
                            request.structured_output_schema,
                            structured,
                            path="structured_output",
                        )
                    except ToolContractError as exc:
                        raise LlamaCppRuntimeError(f"structured output validation failed: {exc}") from exc
                if not calls and payload_text is None and structured is None:
                    raise LlamaCppRuntimeError("local response envelope contains no output")
                return payload_text, tuple(calls), structured, "tool_calls" if calls else "completed"
        if request.structured_output_schema is not None:
            try:
                structured_payload = self._load_protocol_json(text)
            except LlamaCppRuntimeError as exc:
                raise LlamaCppRuntimeError("local structured output is not valid JSON") from exc
            if not isinstance(structured_payload, dict):
                raise LlamaCppRuntimeError("local structured output must be a JSON object")
            try:
                validate_json_value(
                    request.structured_output_schema,
                    structured_payload,
                    path="structured_output",
                )
            except ToolContractError as exc:
                raise LlamaCppRuntimeError(f"structured output validation failed: {exc}") from exc
            return None, (), structured_payload, "completed"
        return text, (), None, "completed"

    def infer(self, request: LocalInferenceRequest, cancel: threading.Event) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")
        if cancel.is_set():
            raise LocalInferenceCancelled("local generation cancelled before launch")
        with self._process_lock:
            # Freeze profile before prompt hashing or artifact checks begin.
            # This prevents a digest/config race with late resource retuning.
            self._inference_admitted = True
            resource_guard = self._resource_preflight
            if resource_guard is not None:
                self._resource_preflight_checks += 1
        if resource_guard is not None:
            # No prompt or child process is constructed before this check.
            resource_guard()
        started = time.monotonic()

        def interrupt() -> None:
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")
            if time.monotonic() - started >= float(self.config.timeout_seconds):
                raise TimeoutError("local llama.cpp request exceeded its wall-time budget")

        self._assert_artifacts_stable(interrupt=interrupt)
        execution_profile = self.execution_profile_digest
        rendered_prompt = self._render_prompt(request)
        rendered_bytes = len(rendered_prompt.encode("utf-8"))
        if rendered_bytes > 4 * 1024 * 1024:
            raise LlamaCppRuntimeError("rendered local prompt exceeds 4 MiB")
        limits = self.generation_limits()
        output_limit = limits["max_output_utf8_bytes"]
        if request.max_output_tokens > limits["max_output_tokens"]:
            raise LlamaCppRuntimeError("requested output exceeds admitted GGUF completion limit")
        if rendered_bytes + 1 + request.max_output_tokens > limits["max_total_tokens"]:
            raise LlamaCppRuntimeError("rendered input and completion exceed admitted GGUF context")

        with tempfile.TemporaryDirectory(prefix="skeleton-llama-") as temp_name:
            temp_dir = Path(temp_name)
            prompt_file = temp_dir / "prompt.txt"
            stdout_file = temp_dir / "stdout.bin"
            stderr_file = temp_dir / "stderr.bin"
            prompt_file.write_text(rendered_prompt, encoding="utf-8")
            try:
                os.chmod(prompt_file, 0o600)
            except OSError:
                pass
            schema_file: Path | None = None
            generation_schema = self._generation_schema(request)
            if generation_schema is not None:
                schema_file = temp_dir / "response.schema.json"
                schema_file.write_text(
                    _stable_json(generation_schema),
                    encoding="utf-8",
                )
                try:
                    os.chmod(schema_file, 0o600)
                except OSError:
                    pass
            command = self._command(
                prompt_file,
                request,
                schema_file=schema_file,
            )
            # Prompt content reaches the child only through the private file.
            # Substring searches of argv falsely reject legitimate short
            # prompts that happen to occur in an executable path or flag.
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled before launch")

            with stdout_file.open("wb") as stdout_handle, stderr_file.open("wb") as stderr_handle:
                with self._process_lock:
                    self._spawning_processes += 1
                try:
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=temp_dir,
                        env=self._child_environment(temp_dir),
                        shell=False,
                        start_new_session=(os.name != "nt"),
                        close_fds=True,
                        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0),
                    )
                except BaseException:
                    with self._process_lock:
                        self._spawning_processes -= 1
                    raise
                with self._process_lock:
                    self._spawning_processes -= 1
                    self._active_processes.add(process.pid)
                    self._processes_started += 1
                timed_out = False
                output_overflow = False
                stderr_overflow = False
                stdout_overflow_event = threading.Event()
                stderr_overflow_event = threading.Event()
                pump_errors: list[BaseException] = []
                pumps: list[threading.Thread] = []

                def capture(stream: Any, target: Any, maximum: int, overflow: threading.Event) -> None:
                    written = 0
                    try:
                        read = getattr(stream, "read1", stream.read)
                        while True:
                            chunk = read(65_536)
                            if not chunk:
                                break
                            remaining = max(0, maximum + 1 - written)
                            retained = chunk[:remaining]
                            if retained:
                                target.write(retained)
                                target.flush()
                                written += len(retained)
                            if written > maximum or len(chunk) > remaining:
                                overflow.set()
                            # Continue draining a full pipe until termination;
                            # neither memory nor private files grow past cap+1.
                    except BaseException as exc:
                        pump_errors.append(exc)
                    finally:
                        try:
                            stream.close()
                        except OSError as exc:
                            pump_errors.append(exc)

                stop_output_end: int | None = None
                stop_markers = tuple(marker.encode("utf-8") for marker in request.stop)
                stop_tail = b""
                stop_scanned = 0
                tail_size = max((len(marker) - 1 for marker in stop_markers), default=0)
                try:
                    if process.stdout is None or process.stderr is None:
                        raise LlamaCppRuntimeError("local runtime output pipes are unavailable")
                    for name, stream, target, maximum, overflow in (
                        ("stdout", process.stdout, stdout_handle, output_limit, stdout_overflow_event),
                        ("stderr", process.stderr, stderr_handle, self.config.max_stderr_bytes, stderr_overflow_event),
                    ):
                        pump = threading.Thread(
                            target=capture, args=(stream, target, maximum, overflow),
                            name="skeleton-llama-" + name, daemon=False,
                        )
                        pumps.append(pump)
                        pump.start()
                    while process.poll() is None:
                        if cancel.is_set():
                            raise LocalInferenceCancelled("local generation cancelled")
                        if time.monotonic() - started > float(self.config.timeout_seconds):
                            timed_out = True
                            break
                        if stdout_overflow_event.is_set():
                            output_overflow = True
                            break
                        if stderr_overflow_event.is_set():
                            stderr_overflow = True
                            break
                        if pump_errors:
                            raise LlamaCppRuntimeError("local runtime output capture failed") from pump_errors[0]
                        if stop_markers:
                            with stdout_file.open("rb") as output_reader:
                                output_reader.seek(stop_scanned)
                                chunk = output_reader.read(65536)
                            if chunk:
                                candidate = stop_tail + chunk
                                matches = [candidate.find(marker) for marker in stop_markers]
                                matches = [offset for offset in matches if offset >= 0]
                                if matches:
                                    stop_output_end = stop_scanned - len(stop_tail) + min(matches)
                                    break
                                stop_scanned += len(chunk)
                                stop_tail = candidate[-tail_size:] if tail_size else b""
                        cancel.wait(0.01)
                finally:
                    # Filesystem errors and interrupted callers must release
                    # the child just as cancellation and output limits do.
                    if process.poll() is None or any(pump.is_alive() for pump in pumps):
                        with self._process_lock:
                            self._draining_processes.add(process.pid)
                            if process.poll() is None:
                                self._termination_requests += 1
                    self._terminate(process)
                    for pump in pumps:
                        while pump.is_alive():
                            pump.join(timeout=0.25)
                    if process.stdout is not None:
                        process.stdout.close()
                    if process.stderr is not None:
                        process.stderr.close()
                    with self._process_lock:
                        self._active_processes.discard(process.pid)
                        self._draining_processes.discard(process.pid)
                        self._processes_exited += 1
                return_code = process.poll()
                if return_code is None:
                    raise LlamaCppRuntimeError("local runtime could not be terminated")
                stdout_handle.flush()
                stderr_handle.flush()
                output_overflow = output_overflow or stdout_overflow_event.is_set()
                stderr_overflow = stderr_overflow or stderr_overflow_event.is_set()

            if pump_errors:
                raise LlamaCppRuntimeError("local runtime output capture failed") from pump_errors[0]
            if timed_out:
                raise TimeoutError(
                    f"local llama.cpp runtime exceeded {self.config.timeout_seconds}s deadline"
                )
            if output_overflow:
                raise LlamaCppRuntimeError("local runtime stdout exceeded configured bound")
            if stderr_overflow:
                raise LlamaCppRuntimeError("local runtime stderr exceeded configured bound")
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")
            # A fast producer can grow past the polling threshold before
            # termination. Never allocate that entire file into memory.
            with stdout_file.open("rb") as handle:
                stdout_bytes = handle.read(output_limit + 1)
            with stderr_file.open("rb") as handle:
                stderr_bytes = handle.read(self.config.max_stderr_bytes + 1)
            if len(stdout_bytes) > output_limit:
                raise LlamaCppRuntimeError("local runtime stdout exceeded configured bound")
            if len(stderr_bytes) > self.config.max_stderr_bytes:
                raise LlamaCppRuntimeError("local runtime stderr exceeded configured bound")
            if return_code != 0 and stop_output_end is None:
                diagnostic = stderr_bytes.decode("utf-8", errors="replace").strip()[-4096:]
                raise LlamaCppRuntimeError(f"local runtime exited with code {return_code}: {diagnostic}")
            kv_observation = observe_native_kv_placement(stderr_bytes)
            if (self.config.kv_cache_location == "host"
                    and kv_observation["reported_device_kv_bytes"] > 0):
                raise LlamaCppRuntimeError(
                    "native llama.cpp reported GPU KV buffers despite the "
                    "pinned host-only KV placement request"
                )

            self._assert_artifacts_stable(interrupt=interrupt)
            if self.execution_profile_digest != execution_profile:
                raise LlamaCppRuntimeError("local execution policy changed during generation")
            visible_bytes = stdout_bytes if stop_output_end is None else stdout_bytes[:stop_output_end]
            raw = visible_bytes.decode("utf-8", errors="strict")
            if request.stop:
                matches = [raw.find(marker) for marker in request.stop]
                matches = [position for position in matches if position >= 0]
                if matches:
                    raw = raw[: min(matches)]
            # Operator-declared completion protocol only: the exact fixed
            # upstream EOG trailer is outside generated content. Preserve the
            # full original stdout checksum below. No JSON substring recovery.
            if self.config.output_framing == "llama_completion_eog":
                # b11429 emits EOG LF, then a fixed final pair of LFs. The
                # single-LF form remains the explicit older completion form.
                for trailer in _COMPLETION_EOG_TRAILERS:
                    if raw.endswith(trailer):
                        raw = raw[: -len(trailer)]
                        break
            text, tool_calls, structured, finish_reason = self._parse_output(raw, request)
            input_estimate = rendered_bytes + 1
            output_estimate = min(request.max_output_tokens, len(raw.encode("utf-8")) + 1)
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")
            response_digest = _digest(
                {
                    "runtime": self.runtime_digest,
                    "model": self.model_digest,
                    "request": request.digest,
                    "stdout": hashlib.sha256(stdout_bytes).hexdigest(),
                    "execution_profile": execution_profile,
                }
            )[:32]
            response_id = (
                "local:llama:" + self.runtime_digest + ":" + self.model_digest + ":" + response_digest
            )
            with self._process_lock:
                self._last_kv_observation = dict(kv_observation)
            return LocalInferenceResult(
                text=text,
                model_id=self.model_id,
                model_digest=self.model_digest,
                input_tokens=input_estimate,
                output_tokens=output_estimate,
                finish_reason=finish_reason,
                response_id=response_id,
                execution_receipt_digest=_digest(
                    {
                        "schema": "skeleton.llama-cpp.execution-receipt.v1",
                        "raw_stdout_digest": hashlib.sha256(stdout_bytes).hexdigest(),
                        "output_framing": self.config.output_framing,
                        "kv_cache_location_requested": self.config.kv_cache_location,
                        "native_kv_observation": kv_observation,
                        "request": request.digest,
                        "execution_profile": execution_profile,
                        "response_id": response_id,
                        "text": text,
                        "tool_calls": [
                            {
                                "call_id": call.call_id,
                                "tool_id": call.tool_id,
                                "arguments": dict(call.arguments),
                            }
                            for call in tool_calls
                        ],
                        "structured_output": structured,
                        "finish_reason": finish_reason,
                        "input_tokens_estimate": input_estimate,
                        "output_tokens_estimate": output_estimate,
                    }
                ),
                usage_source="local_model_estimate",
                tool_calls=tool_calls,
                structured_output=structured,
                latency_ms=(time.monotonic() - started) * 1000.0,
            )


def build_llama_cpp_adapter(
    config: LlamaCppConfig,
    *,
    cache_size: int = 0,
    default_seed: int = 0,
    consumer_budget: ConsumerHardwareBudget | None = None,
    max_concurrency: int = 1,
    max_queue_size: int = 256,
    max_batch_size: int = 256,
    require_guarded_inference: bool = False,
    guarded_components: Any | None = None,
) -> LocalModelAdapter:
    """Build offline adapter; protected mode has no unguarded fallback."""
    if type(require_guarded_inference) is not bool:
        raise LlamaCppRuntimeError("protected local mode must be explicit")
    if require_guarded_inference:
        from .guarded_composition import ProtectedLocalComponents
        if not isinstance(guarded_components, ProtectedLocalComponents):
            raise LlamaCppRuntimeError("protected local deployment lacks trusted components")
    elif guarded_components is not None:
        raise LlamaCppRuntimeError("protected components require enforced local mode")
    if consumer_budget is not None:
        try:
            model_bytes = Path(config.model_path).stat().st_size
        except OSError as exc:
            raise LlamaCppRuntimeError("cannot size local GGUF for consumer planning") from exc
        config = plan_consumer_llama_cpp(
            config,
            consumer_budget,
            model_bytes=model_bytes,
        ).configuration
    engine = LocalInferenceEngine(
        LlamaCppModel(config),
        cache_size=cache_size,
        max_concurrency=max_concurrency,
        max_queue_size=max_queue_size,
        max_batch_size=max_batch_size,
        require_guarded_context=require_guarded_inference,
    )
    if require_guarded_inference:
        from .guarded_composition import compose_protected_local_adapter
        return compose_protected_local_adapter(
            engine, components=guarded_components, default_seed=default_seed,
        )
    return LocalModelAdapter(engine, default_seed=default_seed)


__all__ = [
    "ArtifactIdentity",
    "ConsumerHardwareBudget",
    "ConsumerLlamaPlan",
    "GgufHeader",
    "GgufServingMetadata",
    "LlamaCppConfig",
    "LlamaCppModel",
    "LlamaCppRuntimeError",
    "build_llama_cpp_adapter",
    "detect_consumer_hardware_budget",
    "estimate_gqa_kv_bytes_per_token",
    "inspect_gguf",
    "plan_consumer_llama_cpp",
]
