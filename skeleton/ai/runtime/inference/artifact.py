"""Content-addressed local model artifacts for offline AI execution."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local import ReferenceNGramModel

_MAX_ARTIFACT_BYTES = 128 * 1024 * 1024


class LocalModelArtifactError(RuntimeError):
    """A local model artifact is malformed, unauthenticated, or unsupported."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalModelArtifactError(f"duplicate JSON key in artifact: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise LocalModelArtifactError("artifact contains non-finite JSON constant: " + value)


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
        raise LocalModelArtifactError("local model artifact is not canonical JSON") from exc


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
    schema = payload.get("schema_version")
    if schema == "skeleton.numpy_recurrent_lm.v1":
        try:
            from .neural import NumpyRecurrentLM
        except ModuleNotFoundError as exc:
            raise LocalModelArtifactError("NumPy is required to load a native neural artifact") from exc
        try:
            return NumpyRecurrentLM.from_dict(payload), schema
        except (TypeError, ValueError, RuntimeError) as exc:
            raise LocalModelArtifactError("native neural artifact failed identity validation") from exc

    if payload.get("kind") == "reference_ngram":
        try:
            return ReferenceNGramModel.from_dict(payload), "reference_ngram"
        except (TypeError, ValueError) as exc:
            raise LocalModelArtifactError(
                "reference model artifact is invalid: identity validation failed"
            ) from exc

    raise LocalModelArtifactError("unsupported local model artifact schema")


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _checked_path(source: Path) -> os.stat_result:
    for component in reversed((source, *source.parents)):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise LocalModelArtifactError("local model artifact symlink is forbidden")
        if component != source and not stat.S_ISDIR(info.st_mode):
            raise LocalModelArtifactError("local model artifact parent must be a directory")
    if not stat.S_ISREG(info.st_mode):
        raise LocalModelArtifactError("local model artifact must be a regular file")
    return info


def _read_artifact_bytes(source: Path) -> bytes:
    """Bound allocation and verify the opened descriptor still owns the named file."""
    descriptor = None
    try:
        before = _checked_path(source)
        if not 1 <= before.st_size <= _MAX_ARTIFACT_BYTES:
            raise LocalModelArtifactError("local model artifact violates byte bounds")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(source, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise LocalModelArtifactError("local model artifact must be a regular file")
        if _file_identity(opened) != _file_identity(before):
            raise LocalModelArtifactError("local model artifact changed before reading")
        remaining = before.st_size + 1
        chunks = []
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        named = _checked_path(source)
        raw = b"".join(chunks)
        if (
            len(raw) != before.st_size
            or _file_identity(after) != _file_identity(before)
            or _file_identity(named) != _file_identity(before)
        ):
            raise LocalModelArtifactError("local model artifact changed while reading")
        return raw
    except OSError as exc:
        raise LocalModelArtifactError("local model artifact is unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_local_model_artifact(path: str | os.PathLike[str]) -> LoadedLocalModel:
    source = Path(os.fspath(path)).expanduser().absolute()
    raw = _read_artifact_bytes(source)
    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise LocalModelArtifactError("local model artifact must be UTF-8 JSON") from exc
    except (ValueError, RecursionError) as exc:
        raise LocalModelArtifactError("local model artifact contains invalid JSON") from exc
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
        raise LocalModelArtifactError("local model output parent is unavailable") from exc
    if not parent.is_dir():
        raise LocalModelArtifactError("local model output parent must be a directory")

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
        raise LocalModelArtifactError("local model artifact could not be written atomically") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    loaded = load_local_model_artifact(destination)
    if loaded.receipt.model_digest != model.model_digest:
        raise LocalModelArtifactError("written artifact model identity differs from in-memory model")
    return loaded.receipt


__all__ = [
    "LoadedLocalModel",
    "LocalModelArtifactError",
    "LocalModelArtifactReceipt",
    "load_local_model_artifact",
    "write_local_model_artifact",
]
