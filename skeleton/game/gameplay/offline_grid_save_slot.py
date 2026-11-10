"""Crash-safe, bounded offline campaign save slots.

The caller supplies the session snapshot.  Slots are regular files in a
user-owned directory; this module never follows a symlink at the slot path.
A committed slot is either the previous complete JSON record or the new one.
"""
from __future__ import annotations

import ctypes
import errno
import json
import math
import os
import secrets
import stat
import sys
from pathlib import Path

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
    """Encode incrementally under the save budget, not after a huge allocation.

    A hostile or buggy caller may supply a snapshot much larger than a legal
    save. json.dumps() would first materialize that entire string. Streaming
    JSONEncoder chunks allows bounded publication admission before allocation
    grows beyond MAX_SAVE_BYTES, while preserving canonical serialization.
    """
    buf = bytearray()
    try:
        encoder = json.JSONEncoder(
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        for text in encoder.iterencode(snapshot):
            piece = text.encode("utf-8")
            if len(piece) > MAX_SAVE_BYTES - len(buf):
                raise SaveSlotError("save exceeds byte budget")
            buf.extend(piece)
    except SaveSlotError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise SaveSlotError("invalid replay snapshot") from exc
    payload = bytes(buf)
    # Mixed key types can render the same textual key: refuse any record that
    # cannot round-trip through the strict duplicate-key JSON reader.
    _decode(payload)
    return payload


def _check_slot(name: str, dfd: int) -> os.stat_result | None:
    try:
        info = os.stat(name, dir_fd=dfd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SaveSlotError("save slot must be a regular single-link file")
    return info


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



def _rename_noreplace(dfd: int, source: str, destination: str) -> None:
    """Atomically publish an inode without overwriting any existing name.

    Python's os.rename() can replace a destination and os.link() briefly
    produces a two-link inode; a crash in that window makes our single-link
    replay contract unreadable. Use operating-system no-replace rename under
    the same opened parent descriptor. Never emulate this with a stat/check.
    """
    if sys.platform.startswith("linux"):
        symbol, flag = "renameat2", 1  # Linux RENAME_NOREPLACE
    elif sys.platform == "darwin":
        symbol, flag = "renameatx_np", 0x00000004  # macOS RENAME_EXCL
    else:
        raise SaveSlotError("atomic create-only publication unavailable")
    try:
        function = getattr(ctypes.CDLL(None, use_errno=True), symbol)
    except (AttributeError, OSError) as exc:
        raise SaveSlotError("atomic create-only publication unavailable") from exc
    function.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    if function(
        dfd, os.fsencode(source), dfd, os.fsencode(destination), flag,
    ) == 0:
        return
    code = ctypes.get_errno()
    if code == errno.EEXIST:
        raise FileExistsError(code, "save destination already exists", destination)
    if code in (errno.ENOSYS, errno.EOPNOTSUPP, errno.ENOTSUP, errno.EINVAL):
        raise SaveSlotError("atomic create-only publication unsupported")
    raise OSError(code, os.strerror(code), destination)


def create_slot(path: Path, snapshot: object) -> None:
    """Create-only crash-consistent publication using native no-replace rename.

    The destination is created in one atomic filesystem operation, and the
    temporary name vanishes in that same operation. Existing slots are never
    overwritten, even if a competing writer publishes between checks.
    """
    path = Path(path)
    payload = _encode(snapshot) + b"\n"
    if len(payload) > MAX_SAVE_BYTES:
        raise SaveSlotError("save exceeds byte budget")
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
        _rename_noreplace(dfd, temporary, path.name)
        created = False
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
    """Read a stable regular file from one anchored directory generation.

    The pre-open inode must equal the descriptor actually opened. After the
    bounded read, both the file metadata and the reachable pathname must
    still identify that same object. No attacker-controlled FIFO, link swap
    or in-place mutation can silently replace this accepted snapshot.
    """
    path = Path(path)
    dfd, parent = _open_parent(path)
    fd: int | None = None
    try:
        entry_before = _check_slot(path.name, dfd)
        # O_NONBLOCK prevents FIFO replacement from hanging the caller while
        # O_NOFOLLOW refuses a final-component symlink. fstat admits regular
        # files only, even after an adversarial stat/open race.
        fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=dfd,
        )
        before = os.fstat(fd)
        if (entry_before is None
                or not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size > MAX_SAVE_BYTES
                or (entry_before.st_dev, entry_before.st_ino) !=
                   (before.st_dev, before.st_ino)):
            raise SaveSlotError("save slot changed during open")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_SAVE_BYTES + 1)
        if len(data) > MAX_SAVE_BYTES:
            raise SaveSlotError("save exceeds byte budget")
        after = os.fstat(fd)
        try:
            reachable = os.stat(path.name, dir_fd=dfd, follow_symlinks=False)
            directory = os.stat(parent, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise SaveSlotError("save path disappeared during read") from exc
        held_dir = os.fstat(dfd)

        def fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int]:
            return (
                info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns,
            )

        if (fingerprint(before) != fingerprint(after)
                or (reachable.st_dev, reachable.st_ino) !=
                   (after.st_dev, after.st_ino)
                or (directory.st_dev, directory.st_ino) !=
                   (held_dir.st_dev, held_dir.st_ino)):
            raise SaveSlotError("save slot changed during read")
        return _decode(data)
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            os.close(dfd)
