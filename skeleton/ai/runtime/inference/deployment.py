"""Digest-pinned deployment manifests for standalone local model runtimes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import threading
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
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class LocalModelDeploymentError(RuntimeError):
    """A local-model deployment manifest or artifact failed closed."""


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
    if reject_symlink and path.is_symlink():
        raise LocalModelDeploymentError(f"{field} symlink is forbidden")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LocalModelDeploymentError(f"{field} does not exist: {path}") from exc
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

    @classmethod
    def load(cls, manifest_path: str | Path) -> "LocalModelDeployment":
        source = Path(manifest_path).expanduser()
        try:
            resolved_manifest = source.resolve(strict=True)
        except OSError as exc:
            raise LocalModelDeploymentError(f"deployment manifest not found: {source}") from exc
        try:
            payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalModelDeploymentError("deployment manifest is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise LocalModelDeploymentError("deployment manifest root must be an object")
        if payload.get("schema_version") != SCHEMA:
            raise LocalModelDeploymentError("unsupported deployment manifest schema")
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
        executable_digest = _digest_field(
            payload.get("executable_sha256"), "executable_sha256"
        )
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
        }
        unknown = set(config) - allowed_config
        if unknown:
            raise LocalModelDeploymentError(
                "unsupported deployment config key(s): "
                + ", ".join(sorted(map(str, unknown)))
            )
        extra_args = config.get("extra_args", [])
        if not isinstance(extra_args, list) or not all(
            isinstance(item, str) for item in extra_args
        ):
            raise LocalModelDeploymentError(
                "config.extra_args must be a list of strings"
            )
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
                reject_model_symlink=True,
                rehash_artifacts_each_run=False,
            )
        except (TypeError, ValueError, OSError) as exc:
            raise LocalModelDeploymentError(
                f"invalid llama.cpp deployment config: {exc}"
            ) from exc
        try:
            gguf = inspect_gguf(model)
        except LlamaCppRuntimeError as exc:
            raise LocalModelDeploymentError(
                f"invalid GGUF model artifact: {exc}"
            ) from exc
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
            manifest_digest=_stable_digest(payload),
        )
        deployment.verify_artifacts()
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
            reject_model_symlink=True,
            rehash_artifacts_each_run=rehash_artifacts_each_run,
        )

    def adapter(
        self,
        *,
        cache_size: int = 0,
        default_seed: int = 0,
        rehash_artifacts_each_run: bool = False,
    ) -> LocalModelAdapter:
        return build_llama_cpp_adapter(
            self.llama_cpp_config(
                rehash_artifacts_each_run=rehash_artifacts_each_run
            ),
            cache_size=cache_size,
            default_seed=default_seed,
        )


def load_local_model_adapter(
    manifest_path: str | Path,
    *,
    cache_size: int = 0,
    default_seed: int = 0,
    rehash_artifacts_each_run: bool = False,
) -> LocalModelAdapter:
    return LocalModelDeployment.load(manifest_path).adapter(
        cache_size=cache_size,
        default_seed=default_seed,
        rehash_artifacts_each_run=rehash_artifacts_each_run,
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
        raise LocalModelDeploymentError(
            "qualification max_output_tokens must be in [1, 256]"
        )
    return LocalInferenceRequest(
        prompt=prompt,
        instructions=(
            "Offline local model qualification. Do not use external services."
        ),
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
    if result.model_digest != deployment.model_sha256:
        raise LocalModelDeploymentError(
            "qualification result model identity drift"
        )
    if result.text is None or not result.text.strip():
        raise LocalModelDeploymentError("qualification produced no textual output")
    response_id = getattr(result, "response_id", None)
    if not isinstance(response_id, str) or not response_id.strip():
        raise LocalModelDeploymentError(
            "qualification result is missing response identity"
        )
    if (
        deployment.executable_sha256 not in response_id
        or deployment.model_sha256 not in response_id
    ):
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
        "output_sha256": hashlib.sha256(
            result.text.encode("utf-8")
        ).hexdigest(),
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
    model = LlamaCppModel(
        deployment.llama_cpp_config(rehash_artifacts_each_run=True)
    )
    try:
        result = await LocalInferenceEngine(model, cache_size=0).generate(
            _qualification_request(
                prompt=prompt,
                max_output_tokens=max_output_tokens,
            )
        )
    except (LlamaCppRuntimeError, OSError, TimeoutError) as exc:
        raise LocalModelDeploymentError(
            f"local model qualification execution failed: {exc}"
        ) from exc
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
    model = LlamaCppModel(
        deployment.llama_cpp_config(rehash_artifacts_each_run=True)
    )
    try:
        result = model.infer(
            _qualification_request(
                prompt=prompt,
                max_output_tokens=max_output_tokens,
            ),
            threading.Event(),
        )
    except (LlamaCppRuntimeError, OSError, TimeoutError) as exc:
        raise LocalModelDeploymentError(
            f"local model qualification execution failed: {exc}"
        ) from exc
    return _qualification_receipt(
        deployment,
        model,
        result,
        prompt=prompt,
    )


__all__ = [
    "LocalModelDeployment",
    "LocalModelDeploymentError",
    "QUALIFICATION_SCHEMA",
    "SCHEMA",
    "load_local_model_adapter",
    "qualify_local_model_deployment",
    "qualify_local_model_deployment_sync",
]
