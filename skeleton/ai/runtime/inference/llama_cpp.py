"""Concrete offline llama.cpp CLI backend for Skeleton local inference.

This backend turns the provider-independent LocalModelBackend contract into a
real process boundary for operator-owned GGUF/open-weight models. It never
uses a shell, never places prompt text in argv, binds both executable and model
artifact identities, bounds process output, observes cooperative cancellation,
and strips hosted-provider/proxy credentials from the child environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Mapping

from skeleton.skills.tool_contract import (
    ToolContractError,
    validate_json_schema,
    validate_json_value,
)

from .local import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalToolCall,
)


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
    "--n-predict",
    "--seed",
    "--temp",
    "--ctx-size",
    "--threads",
    "--batch-size",
    "--gpu-layers",
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
    "-ngl",
    "-j",
    "-jf",
)
_REMOTE_ACQUISITION_FLAGS = {
    "--hf-repo",
    "--hf-file",
    "--model-url",
    "--url",
    "--download",
}
_REMOTE_ACQUISITION_SHORT_FLAGS = ("-hf",)


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
    temperature: float = 0.0
    extra_args: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    reject_model_symlink: bool = True
    rehash_artifacts_each_run: bool = False

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
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not lower <= value <= upper
            ):
                raise ValueError(f"{name} must be in [{lower}, {upper}]")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(float(self.temperature))
            or not 0 <= float(self.temperature) <= 10
        ):
            raise ValueError("temperature must be finite and in [0, 10]")
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
                    or (
                        item.startswith(flag)
                        and len(item) > len(flag)
                        and item[len(flag)] not in {"-", "_"}
                    )
                    for flag in _MANAGED_SHORT_FLAGS
                )
            if managed:
                raise ValueError(f"extra_args may not override managed flag {item}")
            remote = option in _REMOTE_ACQUISITION_FLAGS
            if not item.startswith("--"):
                remote = remote or any(
                    item == flag or item.startswith(flag + "=")
                    for flag in _REMOTE_ACQUISITION_SHORT_FLAGS
                )
            if remote:
                raise ValueError(
                    f"extra_args may not enable remote model acquisition {item}"
                )
            normalized_args.append(item)
        object.__setattr__(self, "extra_args", tuple(normalized_args))

        normalized_env: dict[str, str] = {}
        for key, value in dict(self.environment).items():
            if not isinstance(key, str) or not _ENV_KEY.fullmatch(key):
                raise ValueError(f"invalid environment key {key!r}")
            if key in _PROVIDER_SECRET_NAMES or key in _PROXY_NAMES:
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
            "ram_bytes", "physical_cpu_cores", "kv_bytes_per_token",
            "target_context_tokens", "max_decode_threads", "prefill_batch_tokens",
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
    return layers * kv_heads * (
        key_head_dim * key_bytes_per_element
        + value_head_dim * value_bytes_per_element
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
        raise LlamaCppRuntimeError(
            "GGUF weights, KV cache and runtime headroom exceed consumer RAM budget"
        )
    requested = config.context_size or budget.target_context_tokens
    possible = min(requested, available_for_kv // budget.kv_bytes_per_token)
    context = (possible // 128) * 128
    if context < 128:
        raise LlamaCppRuntimeError("consumer RAM budget cannot support minimum context")
    threads = min(config.threads or budget.physical_cpu_cores,
                  budget.physical_cpu_cores, budget.max_decode_threads)
    batch = min(config.batch_size or budget.prefill_batch_tokens,
                budget.prefill_batch_tokens, context)
    chosen = replace(config, context_size=context, threads=threads, batch_size=batch)
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


def _identity(path_value: str, *, executable: bool, reject_symlink: bool) -> ArtifactIdentity:
    raw = Path(path_value).expanduser()
    if executable and not raw.is_absolute():
        resolved_command = shutil.which(path_value)
        if resolved_command is None:
            raise FileNotFoundError(f"local runtime executable not found: {path_value}")
        raw = Path(resolved_command)
    lexical=Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"local artifact not found: {raw}") from exc
    if reject_symlink and lexical!=resolved:
        raise LlamaCppRuntimeError(
            f"artifact symlinked path component rejected: {raw}"
        )
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
        path=str(resolved), sha256=digest, size_bytes=after.st_size,
        mtime_ns=after.st_mtime_ns, inode=getattr(after, "st_ino", None),
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


class LlamaCppModel:
    """Run an exact, identity-bound local model through llama.cpp's CLI."""

    def __init__(self, config: LlamaCppConfig) -> None:
        if not isinstance(config, LlamaCppConfig):
            raise TypeError("config must be LlamaCppConfig")
        self.config = config
        self._runtime = _identity(config.executable, executable=True, reject_symlink=False)
        self._model = _identity(
            config.model_path, executable=False, reject_symlink=config.reject_model_symlink,
        )
        self._gguf_header = inspect_gguf(Path(self._model.path))
        self.model_id = (
            config.model_id.strip() if config.model_id is not None
            else f"llama.cpp:{Path(self._model.path).stem}:{self._model.sha256[:12]}"
        )

    @property
    def model_digest(self) -> str:
        return self._model.sha256

    @property
    def runtime_digest(self) -> str:
        return self._runtime.sha256

    @property
    def execution_profile_digest(self) -> str:
        """Bind decoding/resource policy without changing executable identity."""
        return _digest({
            "schema": "skeleton.llama-cpp.execution-profile.v1",
            "runtime": self.runtime_digest,
            "model": self.model_digest,
            "context_size": self.config.context_size,
            "threads": self.config.threads,
            "batch_size": self.config.batch_size,
            "gpu_layers": self.config.gpu_layers,
            "temperature": float(self.config.temperature),
            "extra_args": list(self.config.extra_args),
            "timeout_seconds": float(self.config.timeout_seconds),
            "max_output_bytes": self.config.max_output_bytes,
            "max_stderr_bytes": self.config.max_stderr_bytes,
            "environment_digest": _digest(self._effective_environment()),
        })

    @property
    def model_artifact(self) -> ArtifactIdentity:
        return self._model

    @property
    def runtime_artifact(self) -> ArtifactIdentity:
        return self._runtime

    @property
    def gguf_header(self) -> GgufHeader:
        return self._gguf_header

    def _assert_artifacts_stable(self, *, interrupt: Callable[[], None] | None = None) -> None:
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

    def _render_prompt(self, request: LocalInferenceRequest) -> str:
        prompt = request.rendered_input
        if not request.tools:
            if request.structured_output_schema is None:
                return prompt
            return (
                prompt
                + "\n\n[Skeleton local structured-output protocol]\n"
                + "Output exactly one JSON object matching the supplied schema. "
                + "Do not include markdown fences or prose outside the JSON object."
            )
        allowed: list[dict[str, Any]] = []
        seen_tool_ids: set[str] = set()
        for item in request.tools:
            tool_id = str(item.get("tool_id", "")).strip()
            if not tool_id:
                raise LlamaCppRuntimeError("local tool schema missing tool_id")
            if tool_id in seen_tool_ids:
                raise LlamaCppRuntimeError("duplicate local tool_id")
            seen_tool_ids.add(tool_id)
            allowed.append({
                "tool_id": tool_id,
                "description": str(item.get("description", "")),
                "input_schema": item.get("input_schema", {}),
            })
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
            + "Allowed tools: " + _stable_json(allowed)
        )
        return prompt + contract

    def _normalized_structured_output_schema(
        self,
        request: LocalInferenceRequest,
    ) -> dict[str, Any] | None:
        if request.structured_output_schema is None:
            return None
        try:
            schema = validate_json_schema(
                request.structured_output_schema
            )
        except ToolContractError as exc:
            raise LlamaCppRuntimeError(
                f"invalid structured output schema: {exc}"
            ) from exc
        if schema.get("type") not in {None, "object"}:
            raise LlamaCppRuntimeError(
                "local structured output schema must describe an object"
            )
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
            raise LlamaCppRuntimeError(
                "tool response schema requires at least one declared tool_id"
            )
        structured_schema = self._normalized_structured_output_schema(
            request
        )
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["skeleton_local_response"],
            "properties": {
                "skeleton_local_response": {"const": 1},
                "text": {"type": "string", "minLength": 1},
                "structured_output": (
                    {"type": "object"}
                    if structured_schema is None
                    else structured_schema
                ),
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
            self._runtime.path, "-m", self._model.path, "-f", str(prompt_file),
            "-n", str(request.max_output_tokens), "--seed", str(request.seed),
            "--temp", format(float(self.config.temperature), ".12g"), "--no-display-prompt",
        ]
        if self.config.context_size is not None:
            command.extend(("-c", str(self.config.context_size)))
        if self.config.threads is not None:
            command.extend(("-t", str(self.config.threads)))
        if self.config.batch_size is not None:
            command.extend(("-b", str(self.config.batch_size)))
        if self.config.gpu_layers is not None:
            command.extend(("-ngl", str(self.config.gpu_layers)))
        if schema_file is not None:
            command.extend(("--json-schema-file", str(schema_file)))
        command.extend(self.config.extra_args)
        return command

    def _effective_environment(self) -> dict[str, str]:
        env = {
            key: value for key, value in os.environ.items()
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
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
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
            return json.loads(text, object_pairs_hook=unique_object,
                              parse_constant=reject_constant)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise LlamaCppRuntimeError("local model output is not valid bounded JSON") from exc

    def _parse_output(
        self, raw: str, request: LocalInferenceRequest,
    ) -> tuple[str | None, tuple[LocalToolCall, ...], Mapping[str, Any] | None, str]:
        text = raw.strip()
        if not text:
            raise LlamaCppRuntimeError("local runtime produced empty output")
        allowed_tool_ids = {
            str(item.get("tool_id", "")).strip() for item in request.tools
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
                if (
                    structured is not None
                    and request.structured_output_schema is not None
                ):
                    try:
                        validate_json_value(
                            request.structured_output_schema,
                            structured,
                            path="structured_output",
                        )
                    except ToolContractError as exc:
                        raise LlamaCppRuntimeError(
                            f"structured output validation failed: {exc}"
                        ) from exc
                if not calls and payload_text is None and structured is None:
                    raise LlamaCppRuntimeError("local response envelope contains no output")
                return payload_text, tuple(calls), structured, "tool_calls" if calls else "completed"
        if request.structured_output_schema is not None:
            try:
                structured_payload = self._load_protocol_json(text)
            except LlamaCppRuntimeError as exc:
                raise LlamaCppRuntimeError(
                    "local structured output is not valid JSON"
                ) from exc
            if not isinstance(structured_payload, dict):
                raise LlamaCppRuntimeError(
                    "local structured output must be a JSON object"
                )
            try:
                validate_json_value(
                    request.structured_output_schema,
                    structured_payload,
                    path="structured_output",
                )
            except ToolContractError as exc:
                raise LlamaCppRuntimeError(
                    f"structured output validation failed: {exc}"
                ) from exc
            return None, (), structured_payload, "completed"
        return text, (), None, "completed"

    def infer(self, request: LocalInferenceRequest, cancel: threading.Event) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")
        if cancel.is_set():
            raise LocalInferenceCancelled("local generation cancelled before launch")
        started = time.monotonic()

        def interrupt() -> None:
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")
            if time.monotonic() - started >= float(self.config.timeout_seconds):
                raise TimeoutError("local llama.cpp request exceeded its wall-time budget")

        self._assert_artifacts_stable(interrupt=interrupt)
        execution_profile = self.execution_profile_digest
        rendered_prompt = self._render_prompt(request)
        if len(rendered_prompt.encode("utf-8")) > 4 * 1024 * 1024:
            raise LlamaCppRuntimeError("rendered local prompt exceeds 4 MiB")

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
                process = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=stdout_handle, stderr=stderr_handle,
                    cwd=temp_dir, env=self._child_environment(temp_dir), shell=False,
                    start_new_session=(os.name != "nt"), close_fds=(os.name != "nt"),
                )
                timed_out = False
                output_overflow = False
                stderr_overflow = False
                stop_output_end: int | None = None
                stop_markers = tuple(marker.encode("utf-8") for marker in request.stop)
                stop_tail = b""
                stop_scanned = 0
                tail_size = max((len(marker) - 1 for marker in stop_markers), default=0)
                try:
                    while process.poll() is None:
                        if cancel.is_set():
                            raise LocalInferenceCancelled("local generation cancelled")
                        if time.monotonic() - started > float(self.config.timeout_seconds):
                            timed_out = True
                            break
                        if stdout_file.stat().st_size > self.config.max_output_bytes:
                            output_overflow = True
                            break
                        if stderr_file.stat().st_size > self.config.max_stderr_bytes:
                            stderr_overflow = True
                            break
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
                    self._terminate(process)
                return_code = process.poll()
                if return_code is None:
                    raise LlamaCppRuntimeError("local runtime could not be terminated")
                stdout_handle.flush()
                stderr_handle.flush()

            if timed_out:
                raise TimeoutError(f"local llama.cpp runtime exceeded {self.config.timeout_seconds}s deadline")
            if output_overflow:
                raise LlamaCppRuntimeError("local runtime stdout exceeded configured bound")
            if stderr_overflow:
                raise LlamaCppRuntimeError("local runtime stderr exceeded configured bound")
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")
            # A fast producer can grow past the polling threshold before
            # termination. Never allocate that entire file into memory.
            with stdout_file.open("rb") as handle:
                stdout_bytes = handle.read(self.config.max_output_bytes + 1)
            with stderr_file.open("rb") as handle:
                stderr_bytes = handle.read(self.config.max_stderr_bytes + 1)
            if len(stdout_bytes) > self.config.max_output_bytes:
                raise LlamaCppRuntimeError("local runtime stdout exceeded configured bound")
            if len(stderr_bytes) > self.config.max_stderr_bytes:
                raise LlamaCppRuntimeError("local runtime stderr exceeded configured bound")
            if return_code != 0 and stop_output_end is None:
                diagnostic = stderr_bytes.decode("utf-8", errors="replace").strip()[-4096:]
                raise LlamaCppRuntimeError(f"local runtime exited with code {return_code}: {diagnostic}")

            self._assert_artifacts_stable(interrupt=interrupt)
            if self.execution_profile_digest != execution_profile:
                raise LlamaCppRuntimeError("local execution policy changed during generation")
            visible_bytes = (stdout_bytes if stop_output_end is None
                             else stdout_bytes[:stop_output_end])
            raw = visible_bytes.decode("utf-8", errors="strict")
            if request.stop:
                matches = [raw.find(marker) for marker in request.stop]
                matches = [position for position in matches if position >= 0]
                if matches:
                    raw = raw[:min(matches)]
            text, tool_calls, structured, finish_reason = self._parse_output(raw, request)
            input_estimate = _approx_tokens(rendered_prompt)
            output_estimate = _approx_tokens(raw)
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")
            response_digest = _digest({
                "runtime": self.runtime_digest,
                "model": self.model_digest,
                "request": request.digest,
                "stdout": hashlib.sha256(stdout_bytes).hexdigest(),
                "execution_profile": execution_profile,
            })[:32]
            response_id = (
                "local:llama:"
                + self.runtime_digest
                + ":"
                + self.model_digest
                + ":"
                + response_digest
            )
            return LocalInferenceResult(
                text=text,
                model_id=self.model_id,
                model_digest=self.model_digest,
                input_tokens=input_estimate,
                output_tokens=output_estimate,
                finish_reason=finish_reason,
                response_id=response_id,
                execution_receipt_digest=_digest({
                    "schema": "skeleton.llama-cpp.execution-receipt.v1",
                    "request": request.digest,
                    "execution_profile": execution_profile,
                    "response_id": response_id,
                    "text": text,
                    "tool_calls": [
                        {"call_id": call.call_id, "tool_id": call.tool_id,
                         "arguments": dict(call.arguments)} for call in tool_calls
                    ],
                    "structured_output": structured,
                    "finish_reason": finish_reason,
                    "input_tokens_estimate": input_estimate,
                    "output_tokens_estimate": output_estimate,
                }),
                tool_calls=tool_calls,
                structured_output=structured,
                latency_ms=(time.monotonic() - started) * 1000.0,
            )


def build_llama_cpp_adapter(
    config: LlamaCppConfig, *, cache_size: int = 0, default_seed: int = 0,
    consumer_budget: ConsumerHardwareBudget | None = None,
) -> LocalModelAdapter:
    """Build an offline adapter, optionally applying measured consumer limits."""
    if consumer_budget is not None:
        try:
            model_bytes = Path(config.model_path).stat().st_size
        except OSError as exc:
            raise LlamaCppRuntimeError("cannot size local GGUF for consumer planning") from exc
        config = plan_consumer_llama_cpp(
            config, consumer_budget, model_bytes=model_bytes,
        ).configuration
    return LocalModelAdapter(
        LocalInferenceEngine(LlamaCppModel(config), cache_size=cache_size),
        default_seed=default_seed,
    )


__all__ = [
    "ArtifactIdentity",
    "GgufHeader",
    "LlamaCppConfig",
    "LlamaCppModel",
    "LlamaCppRuntimeError",
    "ConsumerHardwareBudget",
    "ConsumerLlamaPlan",
    "detect_consumer_hardware_budget",
    "estimate_gqa_kv_bytes_per_token",
    "plan_consumer_llama_cpp",
    "build_llama_cpp_adapter",
    "inspect_gguf",
]
