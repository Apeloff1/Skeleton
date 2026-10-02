"""Concrete offline llama.cpp CLI backend for Skeleton local inference.

This backend turns the provider-independent LocalModelBackend contract into a
real process boundary for operator-owned GGUF/open-weight models. It never
uses a shell, never places prompt text in argv, binds both executable and model
artifact identities, bounds process output, observes cooperative cancellation,
and strips hosted-provider/proxy credentials from the child environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
from typing import Any, Mapping

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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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
    if reject_symlink and raw.is_symlink():
        raise LlamaCppRuntimeError(f"artifact symlink rejected: {raw}")
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"local artifact not found: {raw}") from exc
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
    def model_artifact(self) -> ArtifactIdentity:
        return self._model

    @property
    def runtime_artifact(self) -> ArtifactIdentity:
        return self._runtime

    @property
    def gguf_header(self) -> GgufHeader:
        return self._gguf_header

    def _assert_artifacts_stable(self) -> None:
        for label, identity in (("runtime", self._runtime), ("model", self._model)):
            if not _stat_matches(identity):
                raise LlamaCppRuntimeError(f"{label} artifact identity changed")
            if self.config.rehash_artifacts_each_run:
                observed = _sha256_file(Path(identity.path))
                if observed != identity.sha256:
                    raise LlamaCppRuntimeError(f"{label} artifact digest changed")
        observed_header = inspect_gguf(Path(self._model.path))
        if observed_header != self._gguf_header:
            raise LlamaCppRuntimeError("GGUF fixed header changed")

    def _render_prompt(self, request: LocalInferenceRequest) -> str:
        prompt = request.rendered_input
        if not request.tools:
            return prompt
        allowed: list[dict[str, Any]] = []
        for item in request.tools:
            tool_id = str(item.get("tool_id", "")).strip()
            if not tool_id:
                raise LlamaCppRuntimeError("local tool schema missing tool_id")
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
            "Allowed tools: " + _stable_json(allowed)
        )
        return prompt + contract

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
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["skeleton_local_response"],
            "properties": {
                "skeleton_local_response": {"const": 1},
                "text": {"type": "string", "minLength": 1},
                "structured_output": {"type": "object"},
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

    def _child_environment(self, temp_dir: Path) -> dict[str, str]:
        env = {
            key: value for key, value in os.environ.items()
            if key in _INHERITED_ENV_ALLOWLIST
            and key not in _PROVIDER_SECRET_NAMES
            and key not in _PROXY_NAMES
        }
        env.update(dict(self.config.environment))
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
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("skeleton_local_response") == 1:
                raw_calls = payload.get("tool_calls", [])
                if not isinstance(raw_calls, list):
                    raise LlamaCppRuntimeError("tool_calls envelope must be a list")
                calls: list[LocalToolCall] = []
                for raw_call in raw_calls:
                    if not isinstance(raw_call, dict):
                        raise LlamaCppRuntimeError("local tool call must be an object")
                    call_id = str(raw_call.get("call_id", "")).strip()
                    tool_id = str(raw_call.get("tool_id", "")).strip()
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
                structured = payload.get("structured_output")
                if structured is not None and not isinstance(structured, dict):
                    raise LlamaCppRuntimeError("structured_output must be an object")
                if not calls and payload_text is None and structured is None:
                    raise LlamaCppRuntimeError("local response envelope contains no output")
                return payload_text, tuple(calls), structured, "tool_calls" if calls else "completed"
        return text, (), None, "completed"

    def infer(self, request: LocalInferenceRequest, cancel: threading.Event) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")
        if cancel.is_set():
            raise LocalInferenceCancelled("local generation cancelled before launch")
        self._assert_artifacts_stable()
        started = time.monotonic()
        rendered_prompt = self._render_prompt(request)

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
            if request.tools:
                schema_file = temp_dir / "tool-response.schema.json"
                schema_file.write_text(
                    _stable_json(self._tool_response_schema(request)),
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
            if any(request.prompt in arg for arg in command):
                raise LlamaCppRuntimeError("prompt text leaked into process argv")

            with stdout_file.open("wb") as stdout_handle, stderr_file.open("wb") as stderr_handle:
                process = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=stdout_handle, stderr=stderr_handle,
                    cwd=temp_dir, env=self._child_environment(temp_dir), shell=False,
                    start_new_session=(os.name != "nt"), close_fds=(os.name != "nt"),
                )
                timed_out = False
                output_overflow = False
                stderr_overflow = False
                while process.poll() is None:
                    if cancel.is_set():
                        self._terminate(process)
                        raise LocalInferenceCancelled("local generation cancelled")
                    if time.monotonic() - started > float(self.config.timeout_seconds):
                        timed_out = True
                        self._terminate(process)
                        break
                    if stdout_file.stat().st_size > self.config.max_output_bytes:
                        output_overflow = True
                        self._terminate(process)
                        break
                    if stderr_file.stat().st_size > self.config.max_stderr_bytes:
                        stderr_overflow = True
                        self._terminate(process)
                        break
                    time.sleep(0.01)
                return_code = process.wait()
                stdout_handle.flush()
                stderr_handle.flush()

            if timed_out:
                raise TimeoutError(f"local llama.cpp runtime exceeded {self.config.timeout_seconds}s deadline")
            if output_overflow:
                raise LlamaCppRuntimeError("local runtime stdout exceeded configured bound")
            if stderr_overflow:
                raise LlamaCppRuntimeError("local runtime stderr exceeded configured bound")
            stdout_bytes = stdout_file.read_bytes()
            stderr_bytes = stderr_file.read_bytes()
            if len(stdout_bytes) > self.config.max_output_bytes:
                raise LlamaCppRuntimeError("local runtime stdout exceeded configured bound")
            if len(stderr_bytes) > self.config.max_stderr_bytes:
                raise LlamaCppRuntimeError("local runtime stderr exceeded configured bound")
            if return_code != 0:
                diagnostic = stderr_bytes.decode("utf-8", errors="replace").strip()[-4096:]
                raise LlamaCppRuntimeError(f"local runtime exited with code {return_code}: {diagnostic}")

            self._assert_artifacts_stable()
            raw = stdout_bytes.decode("utf-8", errors="strict")
            text, tool_calls, structured, finish_reason = self._parse_output(raw, request)
            response_digest = _digest({
                "runtime": self.runtime_digest,
                "model": self.model_digest,
                "request": request.digest,
                "stdout": hashlib.sha256(stdout_bytes).hexdigest(),
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
                input_tokens=_approx_tokens(rendered_prompt),
                output_tokens=_approx_tokens(text or ""),
                finish_reason=finish_reason,
                response_id=response_id,
                tool_calls=tool_calls,
                structured_output=structured,
                latency_ms=(time.monotonic() - started) * 1000.0,
            )


def build_llama_cpp_adapter(
    config: LlamaCppConfig, *, cache_size: int = 0, default_seed: int = 0,
) -> LocalModelAdapter:
    """Construct the canonical provider-neutral adapter around a llama.cpp model."""
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
    "build_llama_cpp_adapter",
    "inspect_gguf",
]
