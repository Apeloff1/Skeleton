"""Content-addressed local model artifacts for offline AI execution."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
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
    runtime_schema = payload.get("schema")
    if runtime_schema == RUNTIME_SCHEMA:
        try:
            from .native_runtime import NativeRuntimeBackendError, NativeRuntimeLocalModel

            return NativeRuntimeLocalModel.from_checkpoint(payload), runtime_schema
        except (NativeRuntimeBackendError, TypeError, ValueError, RuntimeError) as exc:
            raise LocalModelArtifactError("native runtime artifact failed identity validation") from exc

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
            return ReferenceNGramModel.from_dict(payload), ("skeleton.reference_ngram.v1")
        except (TypeError, ValueError) as exc:
            raise LocalModelArtifactError("reference model artifact is invalid") from exc

    raise LocalModelArtifactError("unsupported local model artifact schema")


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _checked_artifact_path(source: Path) -> tuple[os.stat_result, tuple[tuple[int, int], ...]]:
    """Reject existing aliases and nonregular/oversized input before opening."""
    ancestry = []
    for parent in reversed(source.parents):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise LocalModelArtifactError("local model artifact parent symlink is forbidden")
        if not stat.S_ISDIR(info.st_mode):
            raise LocalModelArtifactError("local model artifact parent must be a directory")
        ancestry.append((info.st_dev, info.st_ino))
    info = source.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise LocalModelArtifactError("local model artifact symlink is forbidden")
    if not stat.S_ISREG(info.st_mode):
        raise LocalModelArtifactError("local model artifact must be a regular file")
    if not 1 <= info.st_size <= _MAX_ARTIFACT_BYTES:
        raise LocalModelArtifactError("local model artifact violates byte bounds")
    return info, tuple(ancestry)


def _read_artifact_source(
    source: Path, *, expected_stat: os.stat_result | None = None, retain: bool = True
) -> tuple[bytearray | None, str, os.stat_result]:
    """Read one stable inode, bounded by its admitted size rather than the cap.

    Nonblocking open prevents a regular-file/FIFO race from hanging intake.
    Descriptor identity is checked before any bytes are read, and both the
    descriptor and original non-symlink path must still agree afterward.
    """
    descriptor = None
    try:
        before, ancestry = _checked_artifact_path(source)
        if expected_stat is not None and _file_identity(before) != _file_identity(expected_stat):
            raise LocalModelArtifactError("local model artifact changed while reading")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_BINARY", 0)
        )
        descriptor = os.open(source, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise LocalModelArtifactError("local model artifact must be a regular file")
        if _file_identity(opened) != _file_identity(before):
            raise LocalModelArtifactError("local model artifact changed while reading")
        digest = hashlib.sha256()
        raw = bytearray() if retain else None
        consumed = 0
        limit = before.st_size + 1
        while consumed < limit:
            chunk = os.read(descriptor, min(1024 * 1024, limit - consumed))
            if not chunk:
                break
            consumed += len(chunk)
            digest.update(chunk)
            if raw is not None:
                raw.extend(chunk)
        after = os.fstat(descriptor)
        current, current_ancestry = _checked_artifact_path(source)
        if (
            consumed != before.st_size
            or _file_identity(after) != _file_identity(before)
            or _file_identity(current) != _file_identity(before)
            or current_ancestry != ancestry
        ):
            raise LocalModelArtifactError("local model artifact changed while reading")
        return raw, digest.hexdigest(), before
    except (OSError, ValueError) as exc:
        raise LocalModelArtifactError("local model artifact is unavailable") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as exc:
                raise LocalModelArtifactError("local model artifact descriptor cleanup failed") from exc


def load_local_model_artifact(
    path: str | os.PathLike[str], *, expected_sha256: str | None = None
) -> LoadedLocalModel:
    """Load an existing artifact, checking an optional source pin before parsing."""

    if expected_sha256 is not None and (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise LocalModelArtifactError("expected artifact sha256 must be lowercase SHA-256")
    source = Path(os.fspath(path)).expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    raw, artifact_sha256, initial_stat = _read_artifact_source(source)
    if raw is None:
        raise LocalModelArtifactError("local model artifact content is unavailable")
    if expected_sha256 is not None and artifact_sha256 != expected_sha256:
        raise LocalModelArtifactError("local model artifact differs from its expected digest pin")
    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise LocalModelArtifactError("local model artifact must be UTF-8 JSON") from exc
    except (json.JSONDecodeError, RecursionError) as exc:
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

    if expected_sha256 is not None:
        # A pinned catalog must never publish an activation whose source was
        # replaced while its native graph was being restored. Keep the reread
        # bounded even if the source grows during activation.
        try:
            _, digest, _ = _read_artifact_source(source, expected_stat=initial_stat, retain=False)
        except LocalModelArtifactError as exc:
            raise LocalModelArtifactError("pinned local model artifact changed during activation") from exc
        if digest != expected_sha256:
            raise LocalModelArtifactError("pinned local model artifact changed during activation")

    return LoadedLocalModel(
        model=model,
        receipt=LocalModelArtifactReceipt(
            schema=schema,
            model_id=model_id,
            model_digest=model_digest,
            artifact_sha256=artifact_sha256,
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
    if loaded.receipt.model_digest != getattr(model, "model_digest"):
        raise LocalModelArtifactError("written artifact model identity differs from in-memory model")
    return loaded.receipt


__all__ = [
    "LoadedLocalModel",
    "LocalModelArtifactError",
    "LocalModelArtifactReceipt",
    "load_local_model_artifact",
    "write_local_model_artifact",
]
