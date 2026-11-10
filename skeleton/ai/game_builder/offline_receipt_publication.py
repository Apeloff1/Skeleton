"""Atomic, no-clobber publication of replay-verified offline game receipts.

The caller must first run the canonical verifier. A receipt is a deterministic
record of that completed verification, not a signature, device test, or license.
Publication is POSIX-only until an equivalent handle-safe Windows path exists.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Mapping, Sequence

from .contracts import canonical_digest
from .dual_runtime_verify import (
    DualRuntimeVerificationError, _assert_original_root, _canonical_bytes, _root_fd,
)

_MAX_RECEIPT_BYTES = 256 * 1024
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,126}\.json\Z")


class ReceiptPublicationError(ValueError):
    """A receipt could not be published without violating custody rules."""



def preflight_receipt_destination(
    destination: str | Path, *, protected_roots: Sequence[str | Path],
    authorized: bool,
) -> Path:
    """Read-only, descriptor-pinned destination admission before costly work.

    This check prevents predictable receipt failures from leaving an otherwise
    newly exported game behind. It is NOT a reservation: the publisher repeats
    its authority and no-clobber checks when the verified receipt is written.
    """
    if authorized is not True:
        raise PermissionError("operator authorization required for receipt publication")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ReceiptPublicationError("descriptor-safe receipt publication unavailable")
    target = Path(destination).expanduser().absolute()
    if not _NAME.fullmatch(target.name):
        raise ReceiptPublicationError("receipt filename must be a bounded .json name")
    target_path = os.path.abspath(os.fspath(target))
    for source in protected_roots:
        source_path = os.path.abspath(os.fspath(Path(source).expanduser()))
        if os.path.commonpath((source_path, target_path)) == source_path:
            raise ReceiptPublicationError("receipt must be outside verified source roots")
    try:
        parent_fd = _root_fd(target.parent)
    except (OSError, TypeError, ValueError) as exc:
        raise ReceiptPublicationError("unsafe receipt destination parent") from exc
    try:
        parent = os.fstat(parent_fd)
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022
                or parent.st_uid != os.geteuid()):
            raise ReceiptPublicationError("receipt parent must be owner-controlled")
        _assert_original_root(target.parent, parent_fd)
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ReceiptPublicationError("receipt destination already exists")
        _assert_original_root(target.parent, parent_fd)
    except (DualRuntimeVerificationError, OSError) as exc:
        raise ReceiptPublicationError("unsafe receipt destination") from exc
    finally:
        os.close(parent_fd)
    return target


def publish_verified_receipt(
    receipt: Mapping[str, object], destination: str | Path, *,
    protected_roots: Sequence[str | Path], authorized: bool,
) -> str:
    """Publish canonical JSON at a new owner-controlled path and return its hash.

    The destination must not be inside any source package or batch: writing
    there would invalidate the very inventory being attested. The final name
    is created with an atomic no-clobber hardlink after a private, fsynced
    temporary file has been fully written. Never overwrite an existing receipt.
    """
    if authorized is not True:
        raise PermissionError("operator authorization required for receipt publication")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ReceiptPublicationError("descriptor-safe receipt publication unavailable")
    if (type(receipt) is not dict or type(receipt.get("schema")) is not str
            or not (receipt.get("offline_gameplay_reexecuted") is True
                    or receipt.get("both_cohorts_replayed") is True)):
        raise ReceiptPublicationError("receipt must come from a completed replay verifier")
    if "receipt_digest" in receipt:
        digest = receipt["receipt_digest"]
        body = {key: value for key, value in receipt.items()
                if key != "receipt_digest"}
        if (type(digest) is not str
                or not hmac.compare_digest(digest, canonical_digest(body))):
            raise ReceiptPublicationError("verified receipt digest is inconsistent")
    try:
        data = _canonical_bytes(receipt)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ReceiptPublicationError("receipt is not canonical JSON") from exc
    if len(data) > _MAX_RECEIPT_BYTES:
        raise ReceiptPublicationError("receipt exceeds byte budget")
    target = Path(destination).expanduser().absolute()
    if not _NAME.fullmatch(target.name):
        raise ReceiptPublicationError("receipt filename must be a bounded .json name")
    target_path = os.path.abspath(os.fspath(target))
    for source in protected_roots:
        source_path = os.path.abspath(os.fspath(Path(source).expanduser()))
        if os.path.commonpath((source_path, target_path)) == source_path:
            raise ReceiptPublicationError("receipt must be outside verified source roots")
    try:
        parent_fd = _root_fd(target.parent)
    except (OSError, TypeError, ValueError) as exc:
        raise ReceiptPublicationError("unsafe receipt destination parent") from exc
    temporary = ".receipt-" + secrets.token_hex(16)
    temporary_identity: tuple[int, int] | None = None
    try:
        parent = os.fstat(parent_fd)
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022
                or parent.st_uid != os.geteuid()):
            raise ReceiptPublicationError("receipt parent must be owner-controlled")
        _assert_original_root(target.parent, parent_fd)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        temp_fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
        try:
            info = os.fstat(temp_fd)
            temporary_identity = (info.st_dev, info.st_ino)
            offset = 0
            while offset < len(data):
                written = os.write(temp_fd, data[offset:])
                if written <= 0:
                    raise ReceiptPublicationError("receipt write made no progress")
                offset += written
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        _assert_original_root(target.parent, parent_fd)
        os.link(
            temporary, target.name, src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd, follow_symlinks=False,
        )
        final = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISREG(final.st_mode)
                or (final.st_dev, final.st_ino) != temporary_identity
                or final.st_size != len(data)):
            raise ReceiptPublicationError("published receipt identity changed")
        os.fsync(parent_fd)
        _assert_original_root(target.parent, parent_fd)
        os.unlink(temporary, dir_fd=parent_fd)
        temporary_identity = None
        os.fsync(parent_fd)
        return sha256(data).hexdigest()
    except BaseException as exc:
        # The hardlink is the publication linearization point. A later
        # directory fsync, path-identity check or temporary cleanup failure
        # makes durability uncertain, NOT publication safely reversible.
        # Never unlink the published name: another process may already have
        # observed it. Preserve it for owner-controlled quarantine/recovery;
        # a retry must fail the existing-name no-clobber check.
        # Authorization was checked before entering the publication transaction.
        # Filesystem EPERM during the atomic link is a custody/publication error,
        # not an authorization decision. Keep the public API fail-closed.
        if isinstance(exc, ReceiptPublicationError):
            raise
        if isinstance(exc, DualRuntimeVerificationError):
            raise ReceiptPublicationError("receipt destination changed during publication") from exc
        if isinstance(exc, OSError):
            raise ReceiptPublicationError("atomic receipt publication failed") from exc
        raise
    finally:
        if temporary_identity is not None:
            try:
                leftover = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
                if (leftover.st_dev, leftover.st_ino) == temporary_identity:
                    os.unlink(temporary, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


__all__ = ["ReceiptPublicationError", "preflight_receipt_destination", "publish_verified_receipt"]
