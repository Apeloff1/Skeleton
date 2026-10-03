"""Strict local-model artifact loading for the assembled engine.

This module is intentionally network-free.  It turns one content-addressed,
operator-supplied model artifact into the existing LocalModelBackend contract
without granting the artifact any policy/tool authority.

Supported schemas are explicit and fail closed:
- reference n-gram artifacts already owned by the dependency-free local runtime;
- the optional NumPy recurrent-LM artifact when that backend is materialized.

Unknown schemas, duplicate JSON keys, non-finite JSON constants, oversized
artifacts, and model-digest drift are rejected before engine activation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .local import LocalInferenceEngine, LocalModelAdapter, ReferenceNGramModel


_MAX_LOCAL_MODEL_ARTIFACT_BYTES = 128 * 1024 * 1024


class LocalModelArtifactError(RuntimeError):
    """A configured local model artifact cannot be trusted or loaded."""


def _reject_constant(value: str) -> None:
    raise LocalModelArtifactError(
        f"local model artifact contains non-finite JSON constant: {value}"
    )


def _object_no_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalModelArtifactError(
                f"local model artifact contains duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _bounded_int_env(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise LocalModelArtifactError(
            f"{name} must be an integer"
        ) from exc
    if value < minimum or value > maximum:
        raise LocalModelArtifactError(
            f"{name} must be in [{minimum}, {maximum}]"
        )
    return value


@dataclass(frozen=True, slots=True)
class LocalModelArtifactReceipt:
    """Non-secret identity for the exact artifact activated by the engine."""

    artifact_sha256: str
    artifact_bytes: int
    schema: str
    model_id: str
    model_digest: str

    def __post_init__(self) -> None:
        for name in ("artifact_sha256", "model_digest"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise LocalModelArtifactError(
                    f"{name} must be lowercase sha256"
                )
        if (
            isinstance(self.artifact_bytes, bool)
            or not isinstance(self.artifact_bytes, int)
            or self.artifact_bytes < 1
            or self.artifact_bytes > _MAX_LOCAL_MODEL_ARTIFACT_BYTES
        ):
            raise LocalModelArtifactError("artifact_bytes is outside hard bounds")
        for name in ("schema", "model_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise LocalModelArtifactError(f"{name} must be non-empty")

    @property
    def reference(self) -> str:
        return "local-model-artifact:" + self.artifact_sha256

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.local_model_artifact_receipt.v1",
            "artifact_sha256": self.artifact_sha256,
            "artifact_bytes": self.artifact_bytes,
            "schema": self.schema,
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "reference": self.reference,
        }


@dataclass(frozen=True, slots=True)
class LoadedLocalModel:
    model: object
    receipt: LocalModelArtifactReceipt


def _read_payload(path: str | Path) -> tuple[Mapping[str, Any], bytes]:
    raw_path = str(path).strip()
    if not raw_path:
        raise LocalModelArtifactError("local model artifact path is required")
    artifact = Path(raw_path).expanduser()
    try:
        resolved = artifact.resolve(strict=True)
        stat = resolved.stat()
    except OSError as exc:
        raise LocalModelArtifactError(
            "local model artifact is unavailable"
        ) from exc
    if not resolved.is_file():
        raise LocalModelArtifactError(
            "local model artifact must be a regular file"
        )
    if stat.st_size < 1:
        raise LocalModelArtifactError("local model artifact is empty")
    if stat.st_size > _MAX_LOCAL_MODEL_ARTIFACT_BYTES:
        raise LocalModelArtifactError(
            "local model artifact exceeds hard byte limit"
        )
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise LocalModelArtifactError(
            "local model artifact could not be read"
        ) from exc
    if len(raw) != stat.st_size:
        raise LocalModelArtifactError(
            "local model artifact changed while being read"
        )
    try:
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(
            text,
            object_pairs_hook=_object_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise LocalModelArtifactError(
            "local model artifact must be UTF-8 JSON"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LocalModelArtifactError(
            "local model artifact contains invalid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise LocalModelArtifactError(
            "local model artifact root must be an object"
        )
    return payload, raw


def load_local_model_artifact(path: str | Path) -> LoadedLocalModel:
    """Load one exact local model artifact and validate its model digest."""

    payload, raw = _read_payload(path)
    schema: str
    if payload.get("kind") == "reference_ngram":
        schema = "reference_ngram"
        try:
            model = ReferenceNGramModel.from_dict(payload)
        except (TypeError, ValueError) as exc:
            raise LocalModelArtifactError(
                "reference n-gram artifact is invalid"
            ) from exc
    elif payload.get("schema_version") == "skeleton.numpy_recurrent_lm.v1":
        schema = "skeleton.numpy_recurrent_lm.v1"
        try:
            from .neural import NumpyRecurrentLM
        except (ImportError, ModuleNotFoundError) as exc:
            raise LocalModelArtifactError(
                "NumPy recurrent local-model backend is not materialized"
            ) from exc
        try:
            model = NumpyRecurrentLM.from_dict(payload)
        except Exception as exc:
            raise LocalModelArtifactError(
                "NumPy recurrent local-model artifact is invalid"
            ) from exc
    elif (
        payload.get("schema_version")
        == "skeleton.numpy_gated_recurrent_lm.v1"
    ):
        schema = "skeleton.numpy_gated_recurrent_lm.v1"
        try:
            from .gated_neural import NumpyGatedRecurrentLM
        except (ImportError, ModuleNotFoundError) as exc:
            raise LocalModelArtifactError(
                "NumPy gated recurrent backend is not materialized"
            ) from exc
        try:
            model = NumpyGatedRecurrentLM.from_dict(payload)
        except Exception as exc:
            raise LocalModelArtifactError(
                "NumPy gated recurrent artifact is invalid"
            ) from exc
    else:
        raise LocalModelArtifactError(
            "unsupported local model artifact schema"
        )

    model_id = str(getattr(model, "model_id", "")).strip()
    model_digest = str(getattr(model, "model_digest", "")).strip()
    if (
        not model_id
        or len(model_digest) != 64
        or any(ch not in "0123456789abcdef" for ch in model_digest)
    ):
        raise LocalModelArtifactError(
            "loaded local model has invalid identity"
        )
    receipt = LocalModelArtifactReceipt(
        artifact_sha256=hashlib.sha256(raw).hexdigest(),
        artifact_bytes=len(raw),
        schema=schema,
        model_id=model_id,
        model_digest=model_digest,
    )
    return LoadedLocalModel(model=model, receipt=receipt)


def local_model_adapter_from_env() -> LocalModelAdapter:
    """Construct the engine-owned local adapter from explicit environment state."""

    activation_path = os.getenv(
        "AI_LOCAL_ACTIVATION_MANIFEST",
        "",
    ).strip()
    activation_digest = os.getenv(
        "AI_LOCAL_ACTIVATION_DIGEST",
        "",
    ).strip()
    if activation_path or activation_digest:
        if not activation_path or not activation_digest:
            raise LocalModelArtifactError(
                "AI_LOCAL_ACTIVATION_MANIFEST and "
                "AI_LOCAL_ACTIVATION_DIGEST must be configured together"
            )
        target = os.getenv(
            "AI_LOCAL_ACTIVATION_TARGET",
            "candidate",
        ).strip().lower()
        if target not in {"candidate", "rollback"}:
            raise LocalModelArtifactError(
                "AI_LOCAL_ACTIVATION_TARGET must be candidate or rollback"
            )
        try:
            from skeleton.ai.runtime.product.activation import (
                LocalModelActivationError,
                local_model_adapter_from_activation_manifest,
            )

            adapter = local_model_adapter_from_activation_manifest(
                activation_path,
                expected_manifest_digest=activation_digest,
                target=target,
            )
        except LocalModelActivationError as exc:
            raise LocalModelArtifactError(
                "promoted local model activation manifest is invalid"
            ) from exc

        manifest = adapter.activation_manifest

        lifecycle_path = os.getenv(
            "AI_LOCAL_LIFECYCLE_STATE",
            "",
        ).strip()
        lifecycle_digest = os.getenv(
            "AI_LOCAL_LIFECYCLE_DIGEST",
            "",
        ).strip()
        if not lifecycle_path or not lifecycle_digest:
            raise LocalModelArtifactError(
                "AI_LOCAL_LIFECYCLE_STATE and "
                "AI_LOCAL_LIFECYCLE_DIGEST are required for governed activation"
            )
        try:
            from skeleton.ai.runtime.product.lifecycle import (
                ModelLifecycleError,
                ModelLifecycleRegistry,
                ModelLifecycleState,
            )

            lifecycle = ModelLifecycleRegistry(lifecycle_path)
            actual_lifecycle_digest = lifecycle.state_digest()
            if (
                len(lifecycle_digest) != 64
                or any(
                    char not in "0123456789abcdef"
                    for char in lifecycle_digest
                )
                or lifecycle_digest != actual_lifecycle_digest
            ):
                raise ModelLifecycleError(
                    "deployment-pinned lifecycle state digest mismatch"
                )
            lifecycle_snapshot = lifecycle.snapshot(
                manifest.candidate_model_digest
            )
            required_state = (
                ModelLifecycleState.ACTIVATED
                if adapter.activation_target == "candidate"
                else ModelLifecycleState.ROLLED_BACK
            )
            if lifecycle_snapshot.state is not required_state:
                raise ModelLifecycleError(
                    "lifecycle state does not authorize selected activation target"
                )
            if (
                lifecycle_snapshot.activation_manifest_digest
                != manifest.manifest_digest
            ):
                raise ModelLifecycleError(
                    "lifecycle state activation manifest identity drift"
                )
            if (
                lifecycle_snapshot.promotion_transition_digest
                != manifest.lifecycle_promotion_transition_digest
            ):
                raise ModelLifecycleError(
                    "lifecycle state promotion transition identity drift"
                )
        except ModelLifecycleError as exc:
            raise LocalModelArtifactError(
                "governed local model lifecycle state is invalid"
            ) from exc

        adapter.lifecycle_snapshot = lifecycle_snapshot
        adapter.lifecycle_state_digest = actual_lifecycle_digest
        adapter.lifecycle_state_path = str(lifecycle.state_path)

        direct_path = os.getenv("AI_LOCAL_MODEL_PATH", "").strip()
        if direct_path:
            try:
                direct = Path(direct_path).expanduser().resolve(strict=True)
            except OSError as exc:
                raise LocalModelArtifactError(
                    "AI_LOCAL_MODEL_PATH is unavailable"
                ) from exc
            selected_path = (
                manifest.candidate_path
                if adapter.activation_target == "candidate"
                else manifest.baseline_path
            )
            if str(direct) != selected_path:
                raise LocalModelArtifactError(
                    "AI_LOCAL_MODEL_PATH conflicts with selected activation target"
                )

        cache_raw = os.getenv("AI_LOCAL_MODEL_CACHE_SIZE")
        if cache_raw is not None and cache_raw.strip():
            cache_size = _bounded_int_env(
                "AI_LOCAL_MODEL_CACHE_SIZE",
                manifest.cache_size,
                minimum=0,
                maximum=16_384,
            )
            if cache_size != manifest.cache_size:
                raise LocalModelArtifactError(
                    "AI_LOCAL_MODEL_CACHE_SIZE conflicts with activation manifest"
                )
        seed_raw = os.getenv("AI_LOCAL_MODEL_SEED")
        if seed_raw is not None and seed_raw.strip():
            seed = _bounded_int_env(
                "AI_LOCAL_MODEL_SEED",
                manifest.default_seed,
                minimum=-(2**63),
                maximum=(2**63) - 1,
            )
            if seed != manifest.default_seed:
                raise LocalModelArtifactError(
                    "AI_LOCAL_MODEL_SEED conflicts with activation manifest"
                )
        return adapter

    loose_target = os.getenv("AI_LOCAL_ACTIVATION_TARGET", "").strip()
    if loose_target:
        raise LocalModelArtifactError(
            "AI_LOCAL_ACTIVATION_TARGET requires an activation manifest"
        )

    path = os.getenv("AI_LOCAL_MODEL_PATH", "").strip()
    if not path:
        raise LocalModelArtifactError(
            "AI_LOCAL_MODEL_PATH is required when AI_PROVIDER=local"
        )
    cache_size = _bounded_int_env(
        "AI_LOCAL_MODEL_CACHE_SIZE",
        128,
        minimum=0,
        maximum=16_384,
    )
    default_seed = _bounded_int_env(
        "AI_LOCAL_MODEL_SEED",
        0,
        minimum=-(2**63),
        maximum=(2**63) - 1,
    )
    loaded = load_local_model_artifact(path)
    adapter = LocalModelAdapter(
        LocalInferenceEngine(
            loaded.model,  # type: ignore[arg-type]
            cache_size=cache_size,
        ),
        default_seed=default_seed,
    )
    # Direct path activation remains the compatibility/operator bootstrap path.
    # Governed learning promotion uses the digest-pinned activation manifest.
    adapter.artifact_receipt = loaded.receipt
    return adapter


__all__ = [
    "LoadedLocalModel",
    "LocalModelArtifactError",
    "LocalModelArtifactReceipt",
    "load_local_model_artifact",
    "local_model_adapter_from_env",
]
