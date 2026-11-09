"""Bounded reference-pointer journal for caller-owned runtime storage.

Checksums detect accidental edits; they do not authenticate a writer. This is
local provenance, not a replacement for the application's authority ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from skeleton.cortex.laws import check

MAX_RECORD_BYTES = 16_384
MAX_LOG_BYTES = 8 * 1024 * 1024
_ROOT: ContextVar[Path | None] = ContextVar("reference_provenance_root", default=None)
_LOCK = threading.RLock()
_FIELDS = {"action", "appid", "title", "url", "license", "dialect", "stored_prose"}


class ReferenceProvenanceError(ValueError):
    """A pointer or journal cannot be safely encoded or verified."""


@contextmanager
def reference_scope(root: Path) -> Iterator[None]:
    """Bind a trusted workspace for nested reference operations in this context."""
    token = _ROOT.set(Path(root).resolve())
    try:
        yield
    finally:
        _ROOT.reset(token)


def runtime_provenance_path(root: Path | None = None) -> Path:
    """Resolve without creating directories or touching the packaged corpus."""
    base = Path(root).resolve() if root is not None else (_ROOT.get() or Path.cwd())
    return base / ".skeleton" / "references" / "provenance.jsonl"


def _validate(pointer: dict) -> None:
    if set(pointer) != _FIELDS:
        raise ReferenceProvenanceError("invalid pointer fields")
    if type(pointer["appid"]) is not int or not 0 < pointer["appid"] < 2**63:
        raise ReferenceProvenanceError("invalid appid")
    for name, limit in (("action", 64), ("title", 512), ("url", 2048), ("license", 160), ("dialect", 160)):
        value = pointer[name]
        if not isinstance(value, str) or len(value) > limit or (name != "dialect" and not value.strip()):
            raise ReferenceProvenanceError(f"invalid {name}")
    if type(pointer["stored_prose"]) is not int or pointer["stored_prose"] != 0:
        raise ReferenceProvenanceError("stored prose is forbidden")
    check(pointer)


def _digest(pointer: dict) -> str:
    # Preserve the original pointer checksum representation, including ASCII
    # escapes and default separators, for historical record verification.
    return hashlib.sha256(json.dumps(pointer, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


def _open_log(path: Path, *, writing: bool) -> int:
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND if writing else os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if path.is_symlink():
        raise ReferenceProvenanceError("journal must not be a symlink")
    fd = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(fd)
        current = path.lstat()
        if not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(current.st_mode):
            raise ReferenceProvenanceError("journal must be a regular file")
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise ReferenceProvenanceError("journal changed while opening")
        return fd
    except BaseException:
        os.close(fd)
        raise


def append_reference(path: Path, ref: dict, *, action: str) -> dict:
    """Append one bounded, flushed pointer; never claim success after I/O failure.

    Threads in this process are serialized. Callers must give a journal one
    process owner; shared multi-process/network-filesystem journaling is not
    provided. A torn tail is preserved and rejected, never silently repaired.
    """
    check(ref)
    dialect = ref.get("dialect")
    if dialect is None:
        dialect = ""
    if not isinstance(dialect, str):
        raise ReferenceProvenanceError("invalid dialect")
    pointer = {"action": action, "appid": ref.get("appid"), "title": ref.get("title"),
               "url": ref.get("url"), "license": ref.get("license"),
               "dialect": dialect[:160], "stored_prose": 0}
    _validate(pointer)
    pointer["sha256"] = _digest(pointer)
    encoded = (json.dumps(pointer, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_RECORD_BYTES:
        raise ReferenceProvenanceError("pointer exceeds byte budget")
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = _open_log(path, writing=True)
        try:
            size = os.fstat(fd).st_size
            if size + len(encoded) > MAX_LOG_BYTES:
                raise ReferenceProvenanceError("journal exceeds byte budget; archive it before continuing")
            if size:
                os.lseek(fd, -1, os.SEEK_END)
                if os.read(fd, 1) != b"\n":
                    raise ReferenceProvenanceError("journal has an incomplete tail")
            if os.write(fd, encoded) != len(encoded):
                raise OSError("incomplete provenance append")
            os.fsync(fd)
        finally:
            os.close(fd)
    return pointer


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReferenceProvenanceError("duplicate pointer field")
        result[key] = value
    return result


def read_reference_log(path: Path, *, max_records: int = 10_000) -> list[dict]:
    """Verify the entire bounded journal before returning any records.

    Absence means no observations. Unreadable, oversized, truncated, malformed,
    or checksum-mismatched state is an error, never an empty successful read.
    """
    if type(max_records) is not int or not 1 <= max_records <= 100_000:
        raise ValueError("max_records must be an integer from 1 to 100000")
    records = []
    with _LOCK:
        try:
            fd = _open_log(path, writing=False)
        except FileNotFoundError:
            return []
        with os.fdopen(fd, "rb") as handle:
            if os.fstat(handle.fileno()).st_size > MAX_LOG_BYTES:
                raise ReferenceProvenanceError("journal exceeds byte budget")
            total = 0
            while raw := handle.readline(MAX_RECORD_BYTES + 1):
                total += len(raw)
                line = len(records) + 1
                if len(raw) > MAX_RECORD_BYTES or total > MAX_LOG_BYTES or line > max_records:
                    raise ReferenceProvenanceError(f"journal budget exceeded at record {line}")
                if not raw.endswith(b"\n"):
                    raise ReferenceProvenanceError(f"incomplete record {line}")
                try:
                    record = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
                    if not isinstance(record, dict) or set(record) != _FIELDS | {"sha256"}:
                        raise ReferenceProvenanceError("invalid record fields")
                    pointer = {key: value for key, value in record.items() if key != "sha256"}
                    _validate(pointer)
                    if record["sha256"] != _digest(pointer):
                        raise ReferenceProvenanceError("checksum mismatch")
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    raise ReferenceProvenanceError(f"invalid provenance record {line}") from None
                records.append(record)
    return records
