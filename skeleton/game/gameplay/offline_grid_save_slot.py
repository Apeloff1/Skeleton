"""Crash-safe, bounded offline campaign save slots.

The caller supplies the session snapshot.  Slots are regular files in a
user-owned directory; this module never follows a symlink at the slot path.
A committed slot is either the previous complete JSON record or the new one.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
import secrets

MAX_SAVE_BYTES = 2_000_000


class SaveSlotError(ValueError):
    """A slot cannot be safely published or restored."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    record: dict[str, object] = {}
    for name, value in pairs:
        if name in record:
            raise SaveSlotError("duplicate save record key")
        record[name] = value
    return record


def _reject_constant(_value: str) -> object:
    raise SaveSlotError("non-finite save value")


def _finite_float(value: str) -> float:
    # RFC-8259 number syntax permits extreme exponents that Python's
    # json.loads converts to Infinity even with parse_constant set.
    result = float(value)
    if not math.isfinite(result):
        raise SaveSlotError("non-finite save value")
    return result


def _decode(payload: bytes) -> object:
    """Strict input matching the writer: no duplicate keys or NaN/Infinity."""
    try:
        return json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except SaveSlotError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SaveSlotError("invalid replay snapshot encoding") from exc


def _encode(snapshot: object) -> bytes:
    try:
        payload = json.dumps(
            snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise SaveSlotError("invalid replay snapshot") from exc
    if len(payload) > MAX_SAVE_BYTES:
        raise SaveSlotError("save exceeds byte budget")
    # Python json.dumps may render heterogeneous dict keys to identical text.
    # Do not publish a record that the strict reader would reject on restore.
    _decode(payload)
    return payload


def _check_slot(name: str, dfd: int) -> None:
    try:
        info = os.stat(name, dir_fd=dfd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SaveSlotError("save slot must be a regular single-link file")


def _open_parent(path: Path) -> tuple[int, Path]:
    """Open every parent path component from the root without symlink traversal.

    Opening only the final directory with O_NOFOLLOW does not protect earlier
    ancestors: an attacker can replace an intermediate component after a
    Path.resolve preflight and before os.open. Descriptor-relative walking
    makes each hop no-follow and anchors subsequent hops to opened directories.
    """
    if path.name in ("", ".", "..") or path.name != os.path.basename(path):
        raise SaveSlotError("invalid slot filename")
    if (not hasattr(os, "supports_dir_fd") or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")
            or not all(fn in os.supports_dir_fd for fn in
                       (os.open, os.stat, os.rename, os.unlink))):
        raise SaveSlotError("descriptor-relative saves unavailable on this platform")
    parent = path.parent.absolute()
    parts = parent.parts
    if not parent.is_absolute() or not parts or any(part in (".", "..") for part in parts[1:]):
        raise SaveSlotError("save parent must be a canonical absolute path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        dfd = os.open(parts[0], flags)
        try:
            for component in parts[1:]:
                next_fd = os.open(component, flags, dir_fd=dfd)
                os.close(dfd)
                dfd = next_fd
            observed = os.stat(parent, follow_symlinks=False)
            held = os.fstat(dfd)
            if (observed.st_dev, observed.st_ino) != (held.st_dev, held.st_ino):
                raise SaveSlotError("save parent changed during open")
            return dfd, parent
        except BaseException:
            os.close(dfd)
            raise
    except OSError as exc:
        raise SaveSlotError("save parent must not contain symlinks or inaccessible components") from exc



def create_slot(path: Path, snapshot: object) -> None:
    """Create-only save under the same directory-descriptor custody as slots.

    The hard link uses the *same* opened directory for source and destination,
    and never replaces an existing directory entry, including a symlink.
    """
    path = Path(path)
    payload = _encode(snapshot) + b"\n"
    if len(payload) > MAX_SAVE_BYTES:
        raise SaveSlotError("save exceeds byte budget")
    if not hasattr(os, "link") or os.link not in os.supports_dir_fd:
        raise SaveSlotError("descriptor-relative create-only saves unavailable")
    dfd, parent = _open_parent(path)
    temporary = ".campaign-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        _check_slot(path.name, dfd)
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=dfd,
        )
        created = True
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        before = os.fstat(dfd)
        after = os.stat(parent, follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise SaveSlotError("save parent changed before publication")
        # Atomic no-clobber publication, not os.rename.
        os.link(
            temporary, path.name,
            src_dir_fd=dfd, dst_dir_fd=dfd,
            follow_symlinks=False,
        )
        os.fsync(dfd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=dfd)
        finally:
            os.close(dfd)


def write_slot(path: Path, snapshot: object) -> None:
    """Publish one complete snapshot, fsyncing file and directory.

    Reject symlink slots and symlinked parent paths. The parent is opened as
    a directory descriptor and publication is relative to that descriptor,
    so parent path replacement cannot redirect the final rename.
    """
    path = Path(path)
    payload = _encode(snapshot)
    dfd, parent = _open_parent(path)
    temporary = ".campaign-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        _check_slot(path.name, dfd)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dfd)
        created = True
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _check_slot(path.name, dfd)
        before = os.fstat(dfd)
        after = os.stat(parent, follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise SaveSlotError("save parent changed before publication")
        os.rename(temporary, path.name, src_dir_fd=dfd, dst_dir_fd=dfd)
        created = False
        os.fsync(dfd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=dfd)
        finally:
            os.close(dfd)


def read_slot(path: Path) -> object:
    path = Path(path)
    dfd, _ = _open_parent(path)
    try:
        _check_slot(path.name, dfd)
        fd = os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=dfd)
    finally:
        os.close(dfd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_SAVE_BYTES:
            raise SaveSlotError("invalid save slot")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_SAVE_BYTES + 1)
        if len(data) > MAX_SAVE_BYTES:
            raise SaveSlotError("save exceeds byte budget")
        return _decode(data)
    finally:
        os.close(fd)
