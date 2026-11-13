"""Private, no-clobber offline game replay save custody.

A save contains only canonical replay actions/state, never executable code or
credentials. All filesystem operations are descriptor-relative on POSIX; the
save digest must be distributed independently for later restoration.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import (
    DualRuntimeVerificationError, _assert_original_root, _root_fd,
)
from skeleton.ai.game_builder.offline_receipt_publication import (
    _NAME, preflight_receipt_destination,
)
from skeleton.ai.game_builder.playable_simulation import MAX_SERIALIZED_REPLAY_BYTES

_HEX = re.compile(r"[0-9a-f]{64}\Z")


class PrivateGameSaveError(ValueError):
    """A private offline save failed custody or integrity validation."""


def _parent(path: str | Path) -> tuple[Path, int]:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PrivateGameSaveError("descriptor-safe offline saves unavailable")
    target = Path(path).expanduser().absolute()
    if not _NAME.fullmatch(target.name):
        raise PrivateGameSaveError("offline save must use a bounded .json filename")
    try:
        fd = _root_fd(target.parent)
    except (DualRuntimeVerificationError, OSError, TypeError, ValueError) as exc:
        raise PrivateGameSaveError("unsafe offline save parent") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise PrivateGameSaveError("save parent must be owner-controlled")
        _assert_original_root(target.parent, fd)
    except BaseException:
        os.close(fd)
        raise
    return target, fd


def read_private_game_save(
    path: str | Path, *, expected_sha256: str, authorized: bool,
) -> bytes:
    """Read a nofollow, single-link save and check a separately held pin."""
    if authorized is not True:
        raise PermissionError("operator authorization required for save restore")
    if type(expected_sha256) is not str or not _HEX.fullmatch(expected_sha256):
        raise PrivateGameSaveError("independent offline save pin required")
    target, fd = _parent(path)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        handle = os.open(target.name, flags, dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.geteuid()
                    or before.st_mode & 0o077
                    or not 0 < before.st_size <= MAX_SERIALIZED_REPLAY_BYTES):
                raise PrivateGameSaveError("save is not an owner-private regular file")
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(handle, min(remaining, 64 * 1024))
                if not chunk:
                    raise PrivateGameSaveError("offline save truncated during restore")
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(handle)
            identity = lambda item: (
                item.st_dev, item.st_ino, item.st_size, item.st_nlink,
                item.st_uid, item.st_mode, item.st_mtime_ns, item.st_ctime_ns,
            )
            if identity(before) != identity(after):
                raise PrivateGameSaveError("offline save changed during restore")
        finally:
            os.close(handle)
        if not hmac.compare_digest(sha256(raw).hexdigest(), expected_sha256):
            raise PrivateGameSaveError("offline save differs from independent pin")
        # Reopen by name after the descriptor-bound read to reject a file
        # replacement while preserving the independent digest authority.
        second = os.open(target.name, flags, dir_fd=fd)
        try:
            newer = os.fstat(second)
            if identity(before) != identity(newer):
                raise PrivateGameSaveError("offline save replaced during restore")
        finally:
            os.close(second)
        _assert_original_root(target.parent, fd)
        return raw
    except (DualRuntimeVerificationError, OSError, ValueError) as exc:
        if isinstance(exc, PrivateGameSaveError):
            raise
        raise PrivateGameSaveError("unsafe offline save source") from exc
    finally:
        os.close(fd)


def publish_private_game_save(
    data: bytes, destination: str | Path, *, protected_roots: Sequence[str | Path],
    authorized: bool,
) -> str:
    """Fsync a new replay save, link atomically, and never overwrite a file."""
    if authorized is not True:
        raise PermissionError("operator authorization required for save publication")
    if type(data) is not bytes or not 0 < len(data) <= MAX_SERIALIZED_REPLAY_BYTES:
        raise PrivateGameSaveError("invalid offline save byte budget")
    preflight_receipt_destination(
        destination, protected_roots=protected_roots, authorized=True,
    )
    target, fd = _parent(destination)
    temporary = ".private-save-" + secrets.token_hex(16)
    identity: tuple[int, int] | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        handle = os.open(temporary, flags, 0o600, dir_fd=fd)
        try:
            info = os.fstat(handle)
            identity = (info.st_dev, info.st_ino)
            offset = 0
            while offset < len(data):
                written = os.write(handle, data[offset:])
                if written <= 0:
                    raise PrivateGameSaveError("offline save write made no progress")
                offset += written
            os.fsync(handle)
        finally:
            os.close(handle)
        _assert_original_root(target.parent, fd)
        os.link(
            temporary, target.name, src_dir_fd=fd, dst_dir_fd=fd,
            follow_symlinks=False,
        )
        final = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISREG(final.st_mode) or final.st_nlink != 2
                or (final.st_dev, final.st_ino) != identity
                or final.st_size != len(data)):
            raise PrivateGameSaveError("offline save publication identity changed")
        os.fsync(fd)
        _assert_original_root(target.parent, fd)
        os.unlink(temporary, dir_fd=fd)
        identity = None
        os.fsync(fd)
        return sha256(data).hexdigest()
    except BaseException as exc:
        # The final hardlink is the publication linearization point.
        # Post-link fsync, verification or cleanup failures mean durability
        # is uncertain. Never unlink a published name: another process may
        # already have observed it, or an attacker may have replaced it.
        # Preserve it for explicit owner-controlled quarantine; retries
        # must fail the existing-name no-clobber preflight.
        if isinstance(exc, (PrivateGameSaveError, PermissionError)):
            raise
        if isinstance(exc, (DualRuntimeVerificationError, OSError)):
            raise PrivateGameSaveError("offline save publication failed") from exc
        raise
    finally:
        if identity is not None:
            try:
                current = os.stat(temporary, dir_fd=fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == identity:
                    os.unlink(temporary, dir_fd=fd)
            except OSError:
                pass
        os.close(fd)


__all__ = [
    "PrivateGameSaveError", "read_private_game_save",
    "publish_private_game_save",
]
