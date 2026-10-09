"""Content-addressed local model artifacts for offline AI execution."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from skeleton.ai.model_runtime.runtime_contracts import RUNTIME_SCHEMA
from .local import ReferenceNGramModel


_MAX_ARTIFACT_BYTES = 128 * 1024 * 1024


class LocalModelArtifactError(RuntimeError):
    """A local model artifact is malformed, unauthenticated, or unsupported."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalModelArtifactError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise LocalModelArtifactError(
        "artifact contains non-finite JSON constant: " + value
    )


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LocalModelArtifactError(
            "local model artifact is not canonical JSON"
        ) from exc


@dataclass(frozen=True, slots=True)
class LocalModelArtifactReceipt:
    schema: str
    model_id: str
    model_digest: str
    artifact_sha256: str
    artifact_bytes: int

    @property
    def reference(self) -> str:
        return "local-model-artifact:" + self.artifact_sha256

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "artifact_sha256": self.artifact_sha256,
            "artifact_bytes": self.artifact_bytes,
            "reference": self.reference,
        }


@dataclass(frozen=True, slots=True)
class LoadedLocalModel:
    model: object
    receipt: LocalModelArtifactReceipt


def _payload_model(payload: Mapping[str, Any]) -> tuple[object, str]:
    runtime_schema = payload.get("schema")
    if runtime_schema == RUNTIME_SCHEMA:
        try:
            from .native_runtime import NativeRuntimeBackendError, NativeRuntimeLocalModel
            return NativeRuntimeLocalModel.from_checkpoint(payload), runtime_schema
        except (NativeRuntimeBackendError, TypeError, ValueError, RuntimeError) as exc:
            raise LocalModelArtifactError(
                "native runtime artifact failed identity validation"
            ) from exc

    schema = payload.get("schema_version")
    if schema == "skeleton.numpy_recurrent_lm.v1":
        try:
            from .neural import NumpyRecurrentLM
        except ModuleNotFoundError as exc:
            raise LocalModelArtifactError(
                "NumPy is required to load a native neural artifact"
            ) from exc
        try:
            return NumpyRecurrentLM.from_dict(payload), schema
        except (TypeError, ValueError, RuntimeError) as exc:
            raise LocalModelArtifactError(
                "native neural artifact failed identity validation"
            ) from exc

    if payload.get("kind") == "reference_ngram":
        try:
            return ReferenceNGramModel.from_dict(payload), (
                "skeleton.reference_ngram.v1"
            )
        except (TypeError, ValueError) as exc:
            raise LocalModelArtifactError(
                "reference model artifact is invalid"
            ) from exc

    raise LocalModelArtifactError("unsupported local model artifact schema")


def load_local_model_artifact(path: str | os.PathLike[str]) -> LoadedLocalModel:
    source = Path(os.fspath(path)).expanduser()
    if source.is_symlink():
        raise LocalModelArtifactError("local model artifact symlink is forbidden")
    try:
        resolved = source.resolve(strict=True)
        stat = resolved.stat()
        if not resolved.is_file():
            raise LocalModelArtifactError("local model artifact must be a regular file")
        if stat.st_size < 1 or stat.st_size > _MAX_ARTIFACT_BYTES:
            raise LocalModelArtifactError("local model artifact violates byte bounds")
        # Reject excessive input *before* allocating, then enforce the cap
        # during read to guard against a file growing after stat().
        with resolved.open("rb") as stream:
            raw = stream.read(_MAX_ARTIFACT_BYTES + 1)
    except OSError as exc:
        raise LocalModelArtifactError("local model artifact is unavailable") from exc
    if len(raw) > _MAX_ARTIFACT_BYTES:
        raise LocalModelArtifactError("local model artifact violates byte bounds")
    if len(raw) != stat.st_size:
        raise LocalModelArtifactError("local model artifact changed while reading")
    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
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
        raise LocalModelArtifactError("local model artifact root must be an object")

    model, schema = _payload_model(payload)
    model_id = getattr(model, "model_id", None)
    model_digest = getattr(model, "model_digest", None)
    if not isinstance(model_id, str) or not model_id.strip():
        raise LocalModelArtifactError("loaded model lacks stable model_id")
    if (
        not isinstance(model_digest, str)
        or len(model_digest) != 64
        or any(ch not in "0123456789abcdef" for ch in model_digest)
    ):
        raise LocalModelArtifactError("loaded model lacks stable model_digest")

    return LoadedLocalModel(
        model=model,
        receipt=LocalModelArtifactReceipt(
            schema=schema,
            model_id=model_id,
            model_digest=model_digest,
            artifact_sha256=hashlib.sha256(raw).hexdigest(),
            artifact_bytes=len(raw),
        ),
    )


def write_local_model_artifact(
    model: object,
    output_path: str | os.PathLike[str],
) -> LocalModelArtifactReceipt:
    if not hasattr(model, "to_dict") or not hasattr(model, "model_digest"):
        raise TypeError("model must expose to_dict() and model_digest")
    payload = model.to_dict()  # type: ignore[attr-defined]
    if not isinstance(payload, Mapping):
        raise LocalModelArtifactError("model to_dict() must return a mapping")
    raw = _canonical_bytes(payload)
    if len(raw) > _MAX_ARTIFACT_BYTES:
        raise LocalModelArtifactError("serialized local model exceeds byte bound")

    destination = Path(os.fspath(output_path)).expanduser()
    if destination.is_symlink():
        raise LocalModelArtifactError("local model output symlink is forbidden")
    try:
        parent = destination.parent.resolve(strict=True)
    except OSError as exc:
        raise LocalModelArtifactError(
            "local model output parent is unavailable"
        ) from exc
    if not parent.is_dir():
        raise LocalModelArtifactError(
            "local model output parent must be a directory"
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=destination.name + ".",
            suffix=".tmp",
            dir=str(parent),
            delete=False,
        ) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, destination)
        temp_path = None
    except OSError as exc:
        raise LocalModelArtifactError(
            "local model artifact could not be written atomically"
        ) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    loaded = load_local_model_artifact(destination)
    if loaded.receipt.model_digest != getattr(model, "model_digest"):
        raise LocalModelArtifactError(
            "written artifact model identity differs from in-memory model"
        )
    return loaded.receipt


__all__ = [
    "LoadedLocalModel",
    "LocalModelArtifactError",
    "LocalModelArtifactReceipt",
    "load_local_model_artifact",
    "write_local_model_artifact",
]
