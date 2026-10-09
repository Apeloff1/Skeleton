"""Operator-controlled offline transcript backups for the standalone app shell.

These backups are portable user data, never authoritative conversation or
execution records. A SHA-256 checksum detects accidental corruption but is
not a signature and must not be treated as evidence of model execution.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Sequence


BACKUP_SCHEMA = "skeleton.app.offline_history_backup.v1"
MAX_MESSAGES = 16
MAX_BACKUP_BYTES = 256 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")


class OfflineHistoryError(ValueError):
    """A local backup cannot be safely written or restored."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise OfflineHistoryError("backup contains invalid JSON data") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _model_digest(value: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise OfflineHistoryError("model identity must be lowercase SHA-256")
    return value


def _history(values: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    if not isinstance(values, (list, tuple)) or len(values) > MAX_MESSAGES or len(values) % 2:
        raise OfflineHistoryError("backup history must contain at most eight complete turns")
    result: list[tuple[str, str]] = []
    for index, item in enumerate(values):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise OfflineHistoryError("malformed offline history message")
        role, content = item
        expected = "user" if index % 2 == 0 else "assistant"
        if role != expected or not isinstance(content, str) or not content.strip():
            raise OfflineHistoryError("offline history must contain complete user/assistant turns")
        limit = 4096 if role == "user" else 65_536
        if len(content) > limit or "\x00" in content:
            raise OfflineHistoryError("offline history message exceeds text policy")
        result.append((role, content))
    return tuple(result)


def _safe_file(path: str | Path, *, create: bool) -> Path:
    source = Path(path).expanduser()
    parent = source.parent
    if not parent.is_dir():
        raise OfflineHistoryError("backup parent directory does not exist")
    if not source.name or source.name in {".", ".."}:
        raise OfflineHistoryError("backup requires a regular file path")
    try:
        if source.is_symlink():
            raise OfflineHistoryError("backup file must not be a symlink")
        if source.exists() and not source.is_file():
            raise OfflineHistoryError("backup path is not a regular file")
        if not create and not source.is_file():
            raise OfflineHistoryError("backup file does not exist")
        return source
    except OSError as exc:
        raise OfflineHistoryError("cannot inspect local backup path") from exc


def _object_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise OfflineHistoryError("duplicate JSON key in offline history backup")
        obj[key] = value
    return obj


def backup_history(
    path: str | Path,
    model_digest: str,
    history: Sequence[tuple[str, str]],
) -> str:
    """Atomically replace one user-chosen backup; returns the payload checksum."""
    model = _model_digest(model_digest)
    turns = _history(history)
    payload = {
        "schema_version": BACKUP_SCHEMA,
        "model_digest": model,
        "history": [[role, content] for role, content in turns],
    }
    checksum = _digest(payload)
    encoded = _canonical({"payload": payload, "sha256": checksum}) + b"\n"
    if len(encoded) > MAX_BACKUP_BYTES:
        raise OfflineHistoryError("offline backup exceeds maximum file size")
    destination = _safe_file(path, create=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".skeleton-offline-", suffix=".tmp",
            dir=destination.parent, delete=False,
        ) as out:
            temporary = out.name
            if os.name == "posix":
                os.fchmod(out.fileno(), 0o600)
            out.write(encoded)
            out.flush()
            os.fsync(out.fileno())
        # Recheck symlink safety just before the atomic replacement.
        _safe_file(destination, create=True)
        os.replace(temporary, destination)
        temporary = None
    except OSError as exc:
        raise OfflineHistoryError("could not atomically write offline history backup") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return checksum


def restore_history(
    path: str | Path,
    model_digest: str,
) -> tuple[tuple[str, str], ...]:
    """Read a bounded backup only for the exact local model identity."""
    model = _model_digest(model_digest)
    source = _safe_file(path, create=False)
    try:
        # Open the actual descriptor with O_NOFOLLOW when supported. A path
        # replaced by a symlink after preflight must not be followed.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(source, flags)
        with os.fdopen(fd, "rb") as inp:
            info = os.fstat(inp.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BACKUP_BYTES:
                raise OfflineHistoryError("offline backup is not a bounded regular file")
            raw = inp.read(MAX_BACKUP_BYTES + 1)
    except OSError as exc:
        raise OfflineHistoryError("cannot read offline history backup") from exc
    if len(raw) > MAX_BACKUP_BYTES:
        raise OfflineHistoryError("offline backup exceeds maximum file size")
    try:
        record = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_no_duplicates)
    except (ValueError, UnicodeError) as exc:
        raise OfflineHistoryError("offline history backup is not valid UTF-8 JSON") from exc
    if not isinstance(record, dict) or set(record) != {"payload", "sha256"}:
        raise OfflineHistoryError("offline history backup envelope is malformed")
    payload, checksum = record["payload"], record["sha256"]
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "model_digest", "history"}
        or payload["schema_version"] != BACKUP_SCHEMA
    ):
        raise OfflineHistoryError("offline history backup schema is unsupported")
    if not isinstance(checksum, str) or _SHA.fullmatch(checksum) is None:
        raise OfflineHistoryError("offline history backup checksum is malformed")
    if not hmac.compare_digest(_digest(payload), checksum):
        raise OfflineHistoryError("offline history backup checksum mismatch")
    if payload["model_digest"] != model:
        raise OfflineHistoryError("offline history backup belongs to another model")
    return _history(payload["history"])


__all__ = [
    "BACKUP_SCHEMA",
    "OfflineHistoryError",
    "backup_history",
    "restore_history",
]
