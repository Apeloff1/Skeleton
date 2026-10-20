"""Digest-pinned deployment manifests for standalone local model runtimes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .llama_cpp import (
    LlamaCppConfig,
    LlamaCppModel,
    LlamaCppRuntimeError,
    build_llama_cpp_adapter,
    inspect_gguf,
)
from .local import (
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
)

SCHEMA = "skeleton.local_model.deployment.v1"
QUALIFICATION_SCHEMA = "skeleton.local_model.qualification.v1"
QWEN3_COMPLETION_CHAT_TEMPLATE = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\\n' + message['content'] + '<|im_end|>\\n' }}"
    "{% endfor %}{% if add_generation_prompt %}"
    "{{ '<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n' }}"
    "{% endif %}"
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_MANIFEST_BYTES = 1024 * 1024


class LocalModelDeploymentError(RuntimeError):
    """A local-model deployment manifest or artifact failed closed."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalModelDeploymentError("deployment manifest contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise LocalModelDeploymentError("deployment manifest contains non-finite JSON values")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise LocalModelDeploymentError(f"cannot hash deployment artifact: {path}") from exc
    return digest.hexdigest()


def _stable_digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolve(
    base: Path,
    value: object,
    field: str,
    *,
    reject_symlink: bool = False,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise LocalModelDeploymentError(f"{field} must be non-empty text")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    lexical = Path(os.path.abspath(path))
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LocalModelDeploymentError(f"{field} does not exist: {path}") from exc
    if reject_symlink and lexical != resolved:
        raise LocalModelDeploymentError(f"{field} symlinked path component is forbidden")
    if not resolved.is_file():
        raise LocalModelDeploymentError(f"{field} must reference a regular file")
    return resolved


def _digest_field(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise LocalModelDeploymentError(f"{field} must be lowercase sha256")
    return value


@dataclass(frozen=True, slots=True)
class LocalModelDeployment:
    manifest_path: Path
    runtime_kind: str
    executable_path: Path
    executable_sha256: str
    model_path: Path
    model_sha256: str
    model_id: str
    gguf_version: int
    gguf_tensor_count: int
    gguf_metadata_count: int
    timeout_seconds: float
    max_output_bytes: int
    max_stderr_bytes: int
    context_size: int | None
    threads: int | None
    batch_size: int | None
    gpu_layers: int | None
    temperature: float
    extra_args: tuple[str, ...]
    manifest_digest: str
    output_framing: str = "raw"

    @classmethod
    def load(
        cls,
        manifest_path: str | Path,
        *,
        expected_sha256: str | None = None,
        max_artifact_bytes: int | None = None,
    ) -> LocalModelDeployment:
        if expected_sha256 is not None:
            _digest_field(expected_sha256, "expected_sha256")
        if max_artifact_bytes is not None and (
            type(max_artifact_bytes) is not int or not 1 <= max_artifact_bytes <= 1024**4
        ):
            raise LocalModelDeploymentError("deployment artifact byte budget must be an integer in [1, 1 TiB]")
        source = Path(manifest_path).expanduser()
        try:
            resolved_manifest = source.resolve(strict=True)
        except OSError as exc:
            raise LocalModelDeploymentError(f"deployment manifest not found: {source}") from exc
        try:
            size = resolved_manifest.stat().st_size
            if not resolved_manifest.is_file() or not 1 <= size <= _MAX_MANIFEST_BYTES:
                raise LocalModelDeploymentError("deployment manifest violates file/byte bounds")
            with resolved_manifest.open("rb") as stream:
                raw = stream.read(_MAX_MANIFEST_BYTES + 1)
            if len(raw) != size or len(raw) > _MAX_MANIFEST_BYTES:
                raise LocalModelDeploymentError("deployment manifest changed or exceeds its byte bound")
            if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
                raise LocalModelDeploymentError("deployment manifest differs from its expected digest pin")
            payload = json.loads(
                raw.decode("utf-8"), object_pairs_hook=_strict_object, parse_constant=_reject_constant
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise LocalModelDeploymentError("deployment manifest is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise LocalModelDeploymentError("deployment manifest root must be an object")
        if payload.get("schema_version") != SCHEMA:
            raise LocalModelDeploymentError("unsupported deployment manifest schema")
        allowed_top_level = {
            "schema_version",
            "runtime_kind",
            "model_id",
            "executable_path",
            "executable_sha256",
            "model_path",
            "model_sha256",
            "config",
        }
        unknown_top_level = set(payload) - allowed_top_level
        if unknown_top_level:
            raise LocalModelDeploymentError(
                "unsupported deployment manifest key(s): " + ", ".join(sorted(map(str, unknown_top_level)))
            )
        if payload.get("runtime_kind") != "llama.cpp-cli":
            raise LocalModelDeploymentError("runtime_kind must be llama.cpp-cli")
        model_id = payload.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise LocalModelDeploymentError("model_id must be non-empty")
        base = resolved_manifest.parent
        executable = _resolve(base, payload.get("executable_path"), "executable_path")
        model = _resolve(
            base,
            payload.get("model_path"),
            "model_path",
            reject_symlink=True,
        )
        if max_artifact_bytes is not None:
            referenced = {path: path.stat().st_size for path in (resolved_manifest, executable, model)}
            if sum(referenced.values()) > max_artifact_bytes:
                raise LocalModelDeploymentError("deployment files exceed the declared catalog byte budget")
        executable_digest = _digest_field(payload.get("executable_sha256"), "executable_sha256")
        model_digest = _digest_field(payload.get("model_sha256"), "model_sha256")
        config = payload.get("config", {})
        if not isinstance(config, dict):
            raise LocalModelDeploymentError("config must be an object")
        allowed_config = {
            "timeout_seconds",
            "max_output_bytes",
            "max_stderr_bytes",
            "context_size",
            "threads",
            "batch_size",
            "gpu_layers",
            "temperature",
            "extra_args",
            "output_framing",
        }
        unknown = set(config) - allowed_config
        if unknown:
            raise LocalModelDeploymentError(
                "unsupported deployment config key(s): " + ", ".join(sorted(map(str, unknown)))
            )
        extra_args = config.get("extra_args", [])
        if not isinstance(extra_args, list) or not all(isinstance(item, str) for item in extra_args):
            raise LocalModelDeploymentError("config.extra_args must be a list of strings")
        try:
            validated = LlamaCppConfig(
                executable=str(executable),
                model_path=str(model),
                model_id=model_id.strip(),
                timeout_seconds=config.get("timeout_seconds", 120.0),
                max_output_bytes=config.get("max_output_bytes", 4 * 1024 * 1024),
                max_stderr_bytes=config.get("max_stderr_bytes", 512 * 1024),
                context_size=config.get("context_size"),
                threads=config.get("threads"),
                batch_size=config.get("batch_size"),
                gpu_layers=config.get("gpu_layers"),
                temperature=config.get("temperature", 0.0),
                extra_args=tuple(extra_args),
                output_framing=config.get("output_framing", "raw"),
                reject_model_symlink=True,
                rehash_artifacts_each_run=False,
            )
        except (TypeError, ValueError, OSError) as exc:
            raise LocalModelDeploymentError(f"invalid llama.cpp deployment config: {exc}") from exc
        if _sha256_file(executable) != executable_digest:
            raise LocalModelDeploymentError("runtime executable digest mismatch")
        if _sha256_file(model) != model_digest:
            raise LocalModelDeploymentError("model artifact digest mismatch")
        try:
            gguf = inspect_gguf(model)
        except LlamaCppRuntimeError as exc:
            raise LocalModelDeploymentError(f"invalid GGUF model artifact: {exc}") from exc
        deployment = cls(
            manifest_path=resolved_manifest,
            runtime_kind="llama.cpp-cli",
            executable_path=executable,
            executable_sha256=executable_digest,
            model_path=model,
            model_sha256=model_digest,
            model_id=model_id.strip(),
            gguf_version=gguf.version,
            gguf_tensor_count=gguf.tensor_count,
            gguf_metadata_count=gguf.metadata_count,
            timeout_seconds=float(validated.timeout_seconds),
            max_output_bytes=validated.max_output_bytes,
            max_stderr_bytes=validated.max_stderr_bytes,
            context_size=validated.context_size,
            threads=validated.threads,
            batch_size=validated.batch_size,
            gpu_layers=validated.gpu_layers,
            temperature=float(validated.temperature),
            extra_args=validated.extra_args,
            output_framing=validated.output_framing,
            manifest_digest=_stable_digest(payload),
        )
        deployment.verify_artifacts()
        if expected_sha256 is not None:
            try:
                with resolved_manifest.open("rb") as stream:
                    admitted_raw = stream.read(_MAX_MANIFEST_BYTES + 1)
            except OSError as exc:
                raise LocalModelDeploymentError("pinned deployment manifest became unavailable") from exc
            if len(admitted_raw) > _MAX_MANIFEST_BYTES or hashlib.sha256(admitted_raw).hexdigest() != expected_sha256:
                raise LocalModelDeploymentError("pinned deployment manifest changed during admission")
        return deployment

    def verify_artifacts(self) -> None:
        if _sha256_file(self.executable_path) != self.executable_sha256:
            raise LocalModelDeploymentError("runtime executable digest mismatch")
        if _sha256_file(self.model_path) != self.model_sha256:
            raise LocalModelDeploymentError("model artifact digest mismatch")

    def llama_cpp_config(
        self,
        *,
        rehash_artifacts_each_run: bool = False,
    ) -> LlamaCppConfig:
        self.verify_artifacts()
        return LlamaCppConfig(
            executable=str(self.executable_path),
            model_path=str(self.model_path),
            model_id=self.model_id,
            timeout_seconds=self.timeout_seconds,
            max_output_bytes=self.max_output_bytes,
            max_stderr_bytes=self.max_stderr_bytes,
            context_size=self.context_size,
            threads=self.threads,
            batch_size=self.batch_size,
            gpu_layers=self.gpu_layers,
            temperature=self.temperature,
            extra_args=self.extra_args,
            output_framing=self.output_framing,
            reject_model_symlink=True,
            rehash_artifacts_each_run=rehash_artifacts_each_run,
        )

    def adapter(
        self,
        *,
        cache_size: int = 0,
        default_seed: int = 0,
        rehash_artifacts_each_run: bool = False,
        max_concurrency: int = 1,
        max_queue_size: int = 256,
        max_batch_size: int = 256,
    ) -> LocalModelAdapter:
        adapter = build_llama_cpp_adapter(
            self.llama_cpp_config(rehash_artifacts_each_run=rehash_artifacts_each_run),
            cache_size=cache_size,
            default_seed=default_seed,
            max_concurrency=max_concurrency,
            max_queue_size=max_queue_size,
            max_batch_size=max_batch_size,
        )
        model = adapter.engine.model
        if not isinstance(model, LlamaCppModel):
            raise LocalModelDeploymentError("deployment runtime identity is invalid")
        if (
            model.model_artifact.sha256 != self.model_sha256
            or model.runtime_artifact.sha256 != self.executable_sha256
        ):
            raise LocalModelDeploymentError("loaded deployment identity mismatch")
        return LocalModelAdapter(
            adapter.engine,
            default_seed=default_seed,
            artifact_status={
                "schema": SCHEMA,
                "model_id": model.model_id,
                "model_digest": model.model_digest,
                "artifact_sha256": model.model_artifact.sha256,
                "artifact_bytes": model.model_artifact.size_bytes,
                "manifest_digest": self.manifest_digest,
                "runtime_digest": model.runtime_digest,
                "runtime_kind": self.runtime_kind,
                "reference": "local-model-deployment:" + self.manifest_digest,
            },
        )


def create_local_model_deployment(
    destination: str | Path,
    *,
    executable_path: str | Path,
    model_path: str | Path,
    model_id: str | None = None,
    context_size: int = 4096,
    threads: int | None = None,
    gpu_layers: int = 0,
    timeout_seconds: float = 120.0,
    output_framing: str = "raw",
    runtime_profile: str = "raw",
) -> LocalModelDeployment:
    """Prepare a pinned configuration from existing files, without execution.

    All admission rules stay in LocalModelDeployment.load/LlamaCppConfig.
    Publish only after that authority validates a private candidate. Hard-link
    publication is create-only: an existing destination is never replaced.
    """
    if not isinstance(runtime_profile, str) or runtime_profile not in {
        "raw",
        "llama-completion-chat",
        "qwen3-completion-chat",
    }:
        raise LocalModelDeploymentError("unsupported local runtime profile")
    extra_args: tuple[str, ...] = ()
    completion_profile = runtime_profile in {"llama-completion-chat", "qwen3-completion-chat"}
    if completion_profile:
        extra_args = (
            "--conversation",
            "--single-turn",
            "--simple-io",
            "--no-perf",
            "--no-escape",
            "--color",
            "off",
            "--jinja",
            "--reasoning",
            "off",
        )
        output_framing = "llama_completion_eog"
        if runtime_profile == "qwen3-completion-chat":
            extra_args += ("--chat-template", QWEN3_COMPLETION_CHAT_TEMPLATE)
    target = Path(destination).expanduser().absolute()
    if not target.parent.is_dir():
        raise LocalModelDeploymentError("manifest destination directory must already exist")
    if target.exists() or target.is_symlink():
        raise LocalModelDeploymentError("manifest destination already exists; choose a new file")
    executable = _resolve(Path.cwd(), str(executable_path), "executable_path")
    model = _resolve(Path.cwd(), str(model_path), "model_path", reject_symlink=True)
    if not os.access(executable, os.X_OK):
        raise LocalModelDeploymentError("selected llama.cpp runtime is not executable")
    # Reject obvious incompatible files before hashing a potentially large model.
    inspect_gguf(model)
    identity = model.stem if model_id is None else model_id
    if not isinstance(identity, str) or not identity.strip() or len(identity.encode("utf-8")) > 256:
        raise LocalModelDeploymentError("model_id must contain 1–256 UTF-8 bytes")
    validated = LlamaCppConfig(
        executable=str(executable),
        model_path=str(model),
        model_id=identity.strip(),
        context_size=context_size,
        threads=threads,
        gpu_layers=gpu_layers,
        timeout_seconds=timeout_seconds,
        output_framing=output_framing,
        reject_model_symlink=True,
        extra_args=extra_args,
        batch_size=512 if completion_profile else None,
    )
    payload = {
        "schema_version": SCHEMA,
        "runtime_kind": "llama.cpp-cli",
        "model_id": validated.model_id,
        "executable_path": str(executable),
        "executable_sha256": _sha256_file(executable),
        "model_path": str(model),
        "model_sha256": _sha256_file(model),
        "config": {
            "context_size": validated.context_size,
            "threads": validated.threads,
            "gpu_layers": validated.gpu_layers,
            "timeout_seconds": validated.timeout_seconds,
            "temperature": 0.0,
            "extra_args": list(validated.extra_args),
            "output_framing": validated.output_framing,
        },
    }
    if completion_profile:
        payload["config"]["batch_size"] = validated.batch_size
    candidate: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix=".skeleton-model-",
            dir=target.parent,
            delete=False,
        ) as handle:
            candidate = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        admitted = LocalModelDeployment.load(candidate)
        os.link(candidate, target)
        return replace(admitted, manifest_path=target)
    except (ValueError, OSError, LlamaCppRuntimeError) as exc:
        raise LocalModelDeploymentError("cannot prepare local model deployment: " + str(exc)) from exc
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)


def load_local_model_adapter(
    manifest_path: str | Path,
    *,
    cache_size: int = 0,
    default_seed: int = 0,
    rehash_artifacts_each_run: bool = False,
    max_concurrency: int = 1,
    max_queue_size: int = 256,
    max_batch_size: int = 256,
) -> LocalModelAdapter:
    return LocalModelDeployment.load(manifest_path).adapter(
        cache_size=cache_size,
        default_seed=default_seed,
        rehash_artifacts_each_run=rehash_artifacts_each_run,
        max_concurrency=max_concurrency,
        max_queue_size=max_queue_size,
        max_batch_size=max_batch_size,
    )


def _qualification_request(
    *,
    prompt: str,
    max_output_tokens: int,
) -> LocalInferenceRequest:
    if not isinstance(prompt, str) or not prompt.strip():
        raise LocalModelDeploymentError("qualification prompt must be non-empty")
    if (
        isinstance(max_output_tokens, bool)
        or not isinstance(max_output_tokens, int)
        or not 1 <= max_output_tokens <= 256
    ):
        raise LocalModelDeploymentError("qualification max_output_tokens must be in [1, 256]")
    return LocalInferenceRequest(
        prompt=prompt,
        instructions=("Offline local model qualification. Do not use external services."),
        max_output_tokens=max_output_tokens,
        seed=0,
    )


def _qualification_receipt(
    deployment: LocalModelDeployment,
    model: LlamaCppModel,
    result: LocalInferenceResult,
    *,
    prompt: str,
) -> dict[str, Any]:
    if not hasattr(result, "model_digest") or not hasattr(result, "text"):
        raise LocalModelDeploymentError("qualification produced invalid result")
    if result.model_digest != deployment.model_sha256 or result.model_id != deployment.model_id:
        raise LocalModelDeploymentError("qualification result model identity drift")
    if result.finish_reason != "completed":
        raise LocalModelDeploymentError("qualification did not reach a completed model response")
    if result.text is None or not result.text.strip():
        raise LocalModelDeploymentError("qualification produced no textual output")
    response_id = getattr(result, "response_id", None)
    if not isinstance(response_id, str) or not response_id.strip():
        raise LocalModelDeploymentError("qualification result is missing response identity")
    if deployment.executable_sha256 not in response_id or deployment.model_sha256 not in response_id:
        raise LocalModelDeploymentError(
            "qualification response identity is not bound to runtime and model digests"
        )
    receipt: dict[str, Any] = {
        "schema_version": QUALIFICATION_SCHEMA,
        "status": "qualified",
        "runtime_kind": deployment.runtime_kind,
        "model_id": deployment.model_id,
        "model_sha256": deployment.model_sha256,
        "executable_sha256": deployment.executable_sha256,
        "manifest_sha256": deployment.manifest_digest,
        "gguf_version": model.gguf_header.version,
        "gguf_tensor_count": model.gguf_header.tensor_count,
        "gguf_metadata_count": model.gguf_header.metadata_count,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "output_sha256": hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
        "response_id": response_id,
        "provider": "local",
        "network_required": False,
        "hosted_provider_credentials_required": False,
    }
    receipt["receipt_digest"] = _stable_digest(receipt)
    return receipt


async def qualify_local_model_deployment(
    manifest_path: str | Path,
    *,
    prompt: str = "Respond with a short offline readiness acknowledgement.",
    max_output_tokens: int = 32,
) -> dict[str, Any]:
    deployment = LocalModelDeployment.load(manifest_path)
    model = LlamaCppModel(deployment.llama_cpp_config(rehash_artifacts_each_run=True))
    try:
        result = await LocalInferenceEngine(model, cache_size=0).generate(
            _qualification_request(
                prompt=prompt,
                max_output_tokens=max_output_tokens,
            )
        )
    except (LlamaCppRuntimeError, OSError, TimeoutError) as exc:
        raise LocalModelDeploymentError(f"local model qualification execution failed: {exc}") from exc
    return _qualification_receipt(
        deployment,
        model,
        result,
        prompt=prompt,
    )


def qualify_local_model_deployment_sync(
    manifest_path: str | Path,
    *,
    prompt: str = "Respond with a short offline readiness acknowledgement.",
    max_output_tokens: int = 32,
) -> dict[str, Any]:
    deployment = LocalModelDeployment.load(manifest_path)
    model = LlamaCppModel(deployment.llama_cpp_config(rehash_artifacts_each_run=True))
    try:
        result = model.infer(
            _qualification_request(
                prompt=prompt,
                max_output_tokens=max_output_tokens,
            ),
            threading.Event(),
        )
    except (LlamaCppRuntimeError, OSError, TimeoutError) as exc:
        raise LocalModelDeploymentError(f"local model qualification execution failed: {exc}") from exc
    return _qualification_receipt(
        deployment,
        model,
        result,
        prompt=prompt,
    )


__all__ = [
    "QUALIFICATION_SCHEMA",
    "QWEN3_COMPLETION_CHAT_TEMPLATE",
    "SCHEMA",
    "LocalModelDeployment",
    "LocalModelDeploymentError",
    "create_local_model_deployment",
    "load_local_model_adapter",
    "qualify_local_model_deployment",
    "qualify_local_model_deployment_sync",
]
