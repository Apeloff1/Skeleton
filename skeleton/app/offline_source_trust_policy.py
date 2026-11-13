"""Independently pinned, fail-closed local Ed25519 source trust policy.

This operator-controlled policy is NOT a remote revocation service, a signature,
a rights grant or proof of publisher identity. The caller supplies the exact
SHA-256 of the policy independently; an older policy pin can authorize older
keys. No automatic policy rollback or freshness claim is made.
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

from skeleton.ai.game_builder.dual_runtime_verify import _assert_original_root, _root_fd
from skeleton.app.offline_archive_signature import (
    _pin, _read_detached_file, verify_offline_source_archive_signature,
)

SCHEMA = "skeleton.app.offline_source_trust_policy.v1"
RECEIPT_SCHEMA = "skeleton.app.offline_source_trust_policy_verification.v1"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,122}\.json\Z")
MAX_POLICY_BYTES = 8192
MAX_ALLOWED_KEYS = 32
MAX_REVOKED_KEYS = 64


class OfflineSourceTrustPolicyError(ValueError):
    """The independently pinned source trust policy cannot admit this key."""


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise OfflineSourceTrustPolicyError("duplicate trust policy key")
        result[key] = value
    return result


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_size, info.st_mode,
        info.st_nlink, info.st_uid, info.st_mtime_ns, info.st_ctime_ns,
    )


def _read_policy(path: str | Path) -> tuple[bytes, tuple[int, ...]]:
    """Open a bounded owner-private regular inode, not a path-following stream."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise OfflineSourceTrustPolicyError("descriptor-safe trust policy unavailable")
    target = Path(path).expanduser().absolute()
    if _NAME.fullmatch(target.name) is None:
        raise OfflineSourceTrustPolicyError("invalid trust policy filename")
    parent_fd = _root_fd(target.parent)
    try:
        parent = os.fstat(parent_fd)
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
                or parent.st_mode & 0o022):
            raise OfflineSourceTrustPolicyError("trust policy parent not owner-controlled")
        _assert_original_root(target.parent, parent_fd)
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        fd = os.open(target.name, flags, dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.geteuid() or before.st_mode & 0o077
                    or not 0 < before.st_size <= MAX_POLICY_BYTES):
                raise OfflineSourceTrustPolicyError("unsafe or oversized trust policy")
            chunks: list[bytes] = []
            remaining = MAX_POLICY_BYTES + 1
            while remaining:
                part = os.read(fd, min(remaining, 4096))
                if not part:
                    break
                chunks.append(part)
                remaining -= len(part)
            raw = b"".join(chunks)
            after = os.fstat(fd)
            if (len(raw) != before.st_size or len(raw) > MAX_POLICY_BYTES
                    or _identity(before) != _identity(after)):
                raise OfflineSourceTrustPolicyError("trust policy changed during read")
        finally:
            os.close(fd)
        named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        _assert_original_root(target.parent, parent_fd)
        if _identity(before) != _identity(named):
            raise OfflineSourceTrustPolicyError("trust policy path replaced during read")
        return raw, _identity(before)
    finally:
        os.close(parent_fd)


def _key_list(value: object, *, name: str, limit: int) -> tuple[str, ...]:
    if type(value) is not list or len(value) > limit:
        raise OfflineSourceTrustPolicyError("invalid " + name + " trust policy list")
    keys: list[str] = []
    for item in value:
        keys.append(_pin(item, name))
    if len(keys) != len(set(keys)):
        raise OfflineSourceTrustPolicyError("duplicate " + name + " trust policy pin")
    return tuple(keys)


def _parse_policy(
    raw: bytes, *, expected_archive_sha256: str,
    expected_manifest_sha256: str,
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    try:
        payload = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                OfflineSourceTrustPolicyError("nonfinite trust policy number")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise OfflineSourceTrustPolicyError("invalid trust policy JSON") from exc
    required = {
        "schema", "epoch", "archive_sha256", "manifest_sha256",
        "authorized_key_sha256", "revoked_key_sha256",
    }
    if type(payload) is not dict or set(payload) != required:
        raise OfflineSourceTrustPolicyError("trust policy fields not canonical")
    if payload["schema"] != SCHEMA:
        raise OfflineSourceTrustPolicyError("unsupported trust policy schema")
    epoch = payload["epoch"]
    if type(epoch) is not int or not 1 <= epoch <= 2**31 - 1:
        raise OfflineSourceTrustPolicyError("invalid trust policy epoch")
    if (_pin(payload["archive_sha256"], "archive") != expected_archive_sha256
            or _pin(payload["manifest_sha256"], "manifest") != expected_manifest_sha256):
        raise OfflineSourceTrustPolicyError("trust policy source scope mismatch")
    allowed = _key_list(
        payload["authorized_key_sha256"], name="authorized", limit=MAX_ALLOWED_KEYS,
    )
    revoked = _key_list(
        payload["revoked_key_sha256"], name="revoked", limit=MAX_REVOKED_KEYS,
    )
    return epoch, allowed, revoked


def verify_policy_signed_offline_source(
    archive: str | Path, public_key_file: str | Path,
    signature_file: str | Path, policy_file: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_public_key_sha256: str,
    expected_policy_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Verify a source signature and an independently pinned local key policy.

    Both the policy and detached public key are read twice. A caller-provided
    policy hash is the sole freshness anchor; the epoch is descriptive only.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, value in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("public key", expected_public_key_sha256),
        ("policy", expected_policy_sha256),
    ):
        _pin(value, name)
    before, identity = _read_policy(policy_file)
    if not hmac.compare_digest(sha256(before).hexdigest(), expected_policy_sha256):
        raise OfflineSourceTrustPolicyError("independent trust policy hash mismatch")
    epoch, allowed, revoked = _parse_policy(
        before, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    key, key_identity = _read_detached_file(public_key_file, length=32)
    if not hmac.compare_digest(sha256(key).hexdigest(), expected_public_key_sha256):
        raise OfflineSourceTrustPolicyError("trust policy key material differs from pin")
    if expected_public_key_sha256 in revoked:
        raise OfflineSourceTrustPolicyError("source signing key explicitly revoked")
    if expected_public_key_sha256 not in allowed:
        raise OfflineSourceTrustPolicyError("source signing key not authorized by policy")
    signature = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    after, after_identity = _read_policy(policy_file)
    key_after, key_after_identity = _read_detached_file(public_key_file, length=32)
    if (before != after or identity != after_identity or key != key_after
            or key_identity != key_after_identity
            or signature.get("source_archive_signature_verified") is not True
            or signature.get("release_certified") is not False):
        raise OfflineSourceTrustPolicyError(
            "policy, key or source signature changed during admission"
        )
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "pinned_policy_signed_source_verified_release_blocked",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "policy_sha256": expected_policy_sha256,
        "policy_epoch_observed": epoch,
        "signed_message_sha256": signature["signed_message_sha256"],
        "source_archive_signature_verified": True,
        "source_archive_integrity_verified": True,
        "key_authorized_by_pinned_policy": True,
        "key_revoked_in_pinned_policy": False,
        "policy_freshness_independently_proven": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
        "read_only": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app verify-policy-signed-source",
        description="Verify source Ed25519 signature against an independently pinned local key policy",
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--expected-policy-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_policy_signed_offline_source(
            args.archive, args.public_key, args.signature, args.policy,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_public_key_sha256=args.expected_public_key_sha256,
            expected_policy_sha256=args.expected_policy_sha256,
            authorized=args.trusted_local_operator,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": RECEIPT_SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "RECEIPT_SCHEMA", "OfflineSourceTrustPolicyError",
    "verify_policy_signed_offline_source", "main",
]
