"""Crash-safe, bounded offline campaign save slots.

The caller supplies the session snapshot.  Slots are regular files in a
user-owned directory; this module never follows a symlink at the slot path.
A committed slot is either the previous complete JSON record or the new one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import secrets

MAX_SAVE_BYTES = 2_000_000


class SaveSlotError(ValueError):
    """A slot cannot be safely published or restored."""


def _encode(snapshot: object) -> bytes:
    try:
        payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SaveSlotError("invalid replay snapshot") from exc
    if len(payload) > MAX_SAVE_BYTES:
        raise SaveSlotError("save exceeds byte budget")
    return payload


def _directory(path: Path) -> Path:
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise SaveSlotError("save directory is not a directory")
    return parent


def _check_slot(name: str, dfd: int) -> None:
    try:
        info = os.stat(name, dir_fd=dfd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SaveSlotError("save slot must be a regular single-link file")


def _open_parent(path: Path) -> tuple[int, Path]:
    if path.name in ("", ".", "..") or path.name != os.path.basename(path):
        raise SaveSlotError("invalid slot filename")
    parent = _directory(path)
    if parent != path.parent.absolute():
        raise SaveSlotError("save parent must not contain symlinks")
    if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
            or not all(fn in os.supports_dir_fd for fn in
                       (os.open, os.stat, os.rename, os.unlink))):
        raise SaveSlotError("descriptor-relative saves unavailable on this platform")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    dfd = os.open(parent, flags)
    if os.stat(parent).st_ino != os.fstat(dfd).st_ino or os.stat(parent).st_dev != os.fstat(dfd).st_dev:
        os.close(dfd)
        raise SaveSlotError("save parent changed during open")
    return dfd, parent


def write_slot(path: Path, snapshot: object) -> None:
    """Publish one complete snapshot, fsyncing file and directory.

    Reject symlink slots and symlinked parent paths. The parent is opened as
    a directory descriptor and publication is relative to that descriptor,
    so parent path replacement cannot redirect the final rename.
    """
    path = Path(path)
    payload = _encode(snapshot)
    parent = _directory(path)
    if parent != path.parent.absolute():
        raise SaveSlotError("save parent must not contain symlinks")
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
        if created:
            os.unlink(temporary, dir_fd=dfd)
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
        return json.loads(data)
    finally:
        os.close(fd)
