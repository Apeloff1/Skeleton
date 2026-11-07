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
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_SAVE_BYTES:
        raise SaveSlotError("save exceeds byte budget")
    return payload


def _directory(path: Path) -> Path:
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise SaveSlotError("save directory is not a directory")
    return parent


def _check_slot(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SaveSlotError("save slot must be a regular unlinked file")


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
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    dfd = os.open(parent, flags)
    temporary = None
    try:
        _check_slot(path)
        fd, temporary = tempfile.mkstemp(prefix=".campaign-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            _check_slot(path)
            os.replace(temporary, path)
            temporary = None
            os.fsync(dfd)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
    finally:
        os.close(dfd)


def read_slot(path: Path) -> object:
    path = Path(path)
    _check_slot(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
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
