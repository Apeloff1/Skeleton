"""Verify a detached Ed25519 signature over an independently pinned source ZIP.

This verifies a source-archive signature, NOT a native executable package,
publisher identity, rights, provenance or consumer device qualification.
No signing private keys are loaded or stored by this module.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from skeleton.ai.game_builder.dual_runtime_verify import _assert_original_root, _root_fd
from skeleton.app.offline_delivery_archive import inspect_offline_game_archive
from skeleton.app.offline_progress_compatibility import _archive_identity

SCHEMA = "skeleton.app.offline_source_archive_ed25519.v1"
DOMAIN = b"Skeleton offline original source archive signature v1\x00"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,122}\.(?:pub|sig)\Z")


class OfflineArchiveSignatureError(ValueError):
    """Detached source signature, public-key custody or archive pin failed."""


def _pin(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise OfflineArchiveSignatureError(
            "independent " + name + " SHA-256 pin required"
        )
    return value


def source_archive_signature_message(
    *, expected_archive_sha256: str, expected_manifest_sha256: str,
) -> bytes:
    """Domain-separated deterministic message for an external Ed25519 signer."""
    archive_pin = _pin(expected_archive_sha256, "archive")
    manifest_pin = _pin(expected_manifest_sha256, "manifest")
    payload = {
        "schema": SCHEMA,
        "archive_sha256": archive_pin,
        "manifest_sha256": manifest_pin,
    }
    return DOMAIN + json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


def _detached_parent(path: str | Path, *, extension: str) -> tuple[Path, int]:
    """Pin an owner-controlled parent; unlike save custody, accept .pub/.sig."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise OfflineArchiveSignatureError("descriptor-safe detached verification unavailable")
    target = Path(path).expanduser().absolute()
    if _NAME.fullmatch(target.name) is None or not target.name.endswith(extension):
        raise OfflineArchiveSignatureError("invalid bounded detached material filename")
    parent_fd = _root_fd(target.parent)
    try:
        info = os.fstat(parent_fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise OfflineArchiveSignatureError("detached material parent is not owner-controlled")
        _assert_original_root(target.parent, parent_fd)
    except BaseException:
        os.close(parent_fd)
        raise
    return target, parent_fd


def _read_detached_file(path: str | Path, *, length: int) -> tuple[bytes, tuple[int, ...]]:
    """Read exact-length owner-controlled file with a descriptor/inode fence."""
    if length not in (32, 64):
        raise OfflineArchiveSignatureError("unsupported detached material length")
    target, parent_fd = _detached_parent(
        path, extension=".pub" if length == 32 else ".sig",
    )
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        fd = os.open(target.name, flags, dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.geteuid() or before.st_mode & 0o022
                    or before.st_size != length):
                raise OfflineArchiveSignatureError(
                    "detached signature material is not a bounded regular file"
                )
            raw = bytearray()
            while len(raw) < length:
                part = os.read(fd, length - len(raw))
                if not part:
                    raise OfflineArchiveSignatureError(
                        "detached signature material truncated"
                    )
                raw.extend(part)
            after = os.fstat(fd)
            identity = lambda item: (
                item.st_dev, item.st_ino, item.st_size, item.st_nlink,
                item.st_uid, item.st_mode, item.st_mtime_ns, item.st_ctime_ns,
            )
            if identity(before) != identity(after):
                raise OfflineArchiveSignatureError(
                    "detached signature material changed during read"
                )
        finally:
            os.close(fd)
        named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        _assert_original_root(target.parent, parent_fd)
        if identity(before) != identity(named):
            raise OfflineArchiveSignatureError(
                "detached signature material replaced during read"
            )
        return bytes(raw), identity(before)
    finally:
        os.close(parent_fd)


def verify_offline_source_archive_signature(
    archive: str | Path,
    public_key_file: str | Path,
    signature_file: str | Path,
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Verify original source bytes and a separately trusted Ed25519 key pin.

    Signature material is read without symlink traversal and checked again
    after archive verification. The private signing key never enters this app.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    message = source_archive_signature_message(
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    key_pin = _pin(expected_public_key_sha256, "public key")
    archive_identity = _archive_identity(archive)
    before = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    key, key_identity = _read_detached_file(public_key_file, length=32)
    signature, signature_identity = _read_detached_file(signature_file, length=64)
    if not hmac.compare_digest(sha256(key).hexdigest(), key_pin):
        raise OfflineArchiveSignatureError("public key differs from independent pin")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        raise OfflineArchiveSignatureError(
            "source archive detached signature invalid"
        ) from exc
    after = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    _, key_after = _read_detached_file(public_key_file, length=32)
    _, signature_after = _read_detached_file(signature_file, length=64)
    if (before != after or archive_identity != _archive_identity(archive)
            or key_identity != key_after or signature_identity != signature_after):
        raise OfflineArchiveSignatureError(
            "archive, public key or signature changed during verification"
        )
    return {
        "schema": SCHEMA,
        "status": "source_archive_signature_verified_consumer_release_blocked",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "public_key_sha256": key_pin,
        "signature_algorithm": "Ed25519",
        "signed_message_sha256": sha256(message).hexdigest(),
        "archived_files": after["archived_files"],
        "source_archive_integrity_verified": True,
        "source_archive_signature_verified": True,
        "private_signing_key_loaded": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "publisher_identity_certified": False,
        "package_signed": False,
        "release_certified": False,
        "read_only": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app verify-archive-signature",
        description="Read-only Ed25519 verification of a pinned original-game ZIP",
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify_offline_source_archive_signature(
            args.archive, args.public_key, args.signature,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_public_key_sha256=args.expected_public_key_sha256,
            authorized=args.trusted_local_operator,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "DOMAIN", "OfflineArchiveSignatureError",
    "source_archive_signature_message", "verify_offline_source_archive_signature",
    "main",
]
