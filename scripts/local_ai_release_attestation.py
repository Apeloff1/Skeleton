#!/usr/bin/env python3
"""Independently verify two Ed25519 signatures over exact offline release claims.

This is a provenance *verification* primitive, not a release signer or an
approval system. Security and release public keys must be supplied by
independent trusted channels OUTSIDE the untrusted evidence bundle; keys
inside that bundle are never accepted. The manifest's digest references
remain claims until each corresponding physical evidence receipt has been
independently retrieved and validated. Successful signatures do not
authorize release or protected Jeeves chat.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

from scripts import local_ai_docker as host

SCHEMA = "skeleton.local-ai.docker.independent-release-claims.v1"
MANIFEST = "release-claims.json"
SIGNATURES = {"security": "security.ed25519.sig",
              "release": "release.ed25519.sig"}
HEX = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
EVIDENCE = (
    "offline_image_receipt_sha256",
    "compose_binding_receipt_sha256",
    "gguf_model_sha256",
    "native_execution_receipt_sha256",
    "protected_chat_receipt_sha256",
    "writer_epoch_receipt_sha256",
    "coherent_restore_receipt_sha256",
    "device_pressure_receipt_sha256",
    "windows_wsl2_receipt_sha256",
    "sbom_sha256",
    "reproducible_build_receipt_sha256",
    "exact_head_ci_matrix_sha256",
)
REQUIRED = frozenset((
    "schema", "status", "source_head", "mode", "signer_domains",
    "release_authorized", "protected_chat_qualified",
    "coherent_recovery_qualified", *EVIDENCE,
))
MAX_MANIFEST = 8192
MAX_PEM = 4096


class ProvenanceError(host.LocalDockerError):
    """No independent release-claim cryptographic admission is available."""


def _private_dir(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ProvenanceError("release evidence directory must be absolute")
    try:
        st = path.lstat()
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid()
                or st.st_mode & 0o077
                or not path.parent.is_dir() or path.parent.is_symlink()
                or path.is_symlink()):
            raise ProvenanceError("release evidence directory must be owner-private")
    except OSError:
        raise ProvenanceError("release evidence directory unavailable") from None
    return path


def _owner_file(path: Path, *, max_bytes: int, private: bool) -> bytes:
    try:
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid()
                or (private and before.st_mode & 0o077)
                or not 0 < before.st_size <= max_bytes):
            raise ProvenanceError("release evidence file ownership or size unsafe")
        with os.fdopen(os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        ), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev, before.st_ino, before.st_size
            ):
                raise ProvenanceError("release evidence file replaced during read")
            value = stream.read(max_bytes + 1)
        after = path.lstat()
        attr = lambda x: (x.st_dev, x.st_ino, x.st_size,
                          x.st_mtime_ns, x.st_ctime_ns)
        if len(value) != before.st_size or attr(before) != attr(after):
            raise ProvenanceError("release evidence file mutated during read")
        return value
    except OSError:
        raise ProvenanceError("release evidence file unavailable") from None


def _duplicates(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ProvenanceError("duplicate signed release claim field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ProvenanceError("non-finite signed release claim")


def _canonical(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("ascii") + b"\n"
    except (TypeError, ValueError, OverflowError):
        raise ProvenanceError("signed claim cannot be canonicalized") from None


def _claims(value: bytes, *, expected_head: str,
            expected_image_receipt_sha256: str) -> dict[str, Any]:
    try:
        claim = json.loads(value.decode("utf-8"),
                           object_pairs_hook=_duplicates,
                           parse_constant=_reject_constant)
    except (ValueError, UnicodeError, TypeError):
        raise ProvenanceError("signed release claim JSON invalid") from None
    if not isinstance(claim, dict) or set(claim) != REQUIRED:
        raise ProvenanceError("signed release claim shape invalid")
    if value != _canonical(claim):
        raise ProvenanceError("signed release claim serialization is noncanonical")
    if (claim.get("schema") != SCHEMA
            or claim.get("status") != "signed_claims_only_not_release_authorized"
            or claim.get("mode") not in ("cpu", "nvidia", "rocm")
            or claim.get("source_head") != expected_head
            or not isinstance(expected_head, str) or not COMMIT.fullmatch(expected_head)
            or claim.get("signer_domains") != ["release", "security"]
            or claim.get("release_authorized") is not False
            or claim.get("protected_chat_qualified") is not False
            or claim.get("coherent_recovery_qualified") is not False):
        raise ProvenanceError("signed release claims attempt authority escalation")
    if (not isinstance(expected_image_receipt_sha256, str)
            or not HEX.fullmatch(expected_image_receipt_sha256)
            or claim["offline_image_receipt_sha256"] != expected_image_receipt_sha256
            or any(not isinstance(claim.get(key), str)
                   or not HEX.fullmatch(claim[key]) for key in EVIDENCE)):
        raise ProvenanceError("signed claim contains unsupported evidence identity")
    return claim


def verify_signed_release_claims(
    directory: Path, security_public_key: Path, release_public_key: Path, *,
    expected_head: str, expected_image_receipt_sha256: str,
) -> dict[str, Any]:
    """Read-only verified signatures; *never* an autonomous release warrant."""
    folder = _private_dir(directory)
    if {p.name for p in folder.iterdir()} != {MANIFEST} | set(SIGNATURES.values()):
        raise ProvenanceError("release claims directory contains undeclared files")
    if (not isinstance(security_public_key, Path)
            or not isinstance(release_public_key, Path)
            or not security_public_key.is_absolute()
            or not release_public_key.is_absolute()):
        raise ProvenanceError("independent external public keys are mandatory")
    for key in (security_public_key, release_public_key):
        if (key == folder or folder in key.parents
                or key.is_symlink() or key.parent.is_symlink()):
            raise ProvenanceError("public key inside evidence bundle is not trusted")
    sec = _owner_file(security_public_key, max_bytes=MAX_PEM, private=False)
    rel = _owner_file(release_public_key, max_bytes=MAX_PEM, private=False)
    if (sec == rel or hashlib.sha256(sec).digest() == hashlib.sha256(rel).digest()
            or not sec.startswith(b"-----BEGIN PUBLIC KEY-----")
            or not rel.startswith(b"-----BEGIN PUBLIC KEY-----")
            or b"PRIVATE" in sec or b"PRIVATE" in rel):
        raise ProvenanceError("distinct externally pinned public authorities required")
    manifest = _owner_file(folder / MANIFEST, max_bytes=MAX_MANIFEST, private=True)
    _claims(manifest, expected_head=expected_head,
            expected_image_receipt_sha256=expected_image_receipt_sha256)
    for name, public in (("security", security_public_key),
                         ("release", release_public_key)):
        sig = folder / SIGNATURES[name]
        if len(_owner_file(sig, max_bytes=64, private=True)) != 64:
            raise ProvenanceError("Ed25519 signature has invalid length")
        try:
            completed = subprocess.run([
                "openssl", "pkeyutl", "-verify", "-pubin",
                "-inkey", str(public), "-rawin",
                "-in", str(folder / MANIFEST),
                "-sigfile", str(sig),
            ], text=True, capture_output=True, check=False, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            raise ProvenanceError("independent signature verifier unavailable") from None
        if completed.returncode != 0:
            # Never expose raw openssl diagnostics or local file paths.
            raise ProvenanceError("independent Ed25519 signature verification failed")
    if _owner_file(folder / MANIFEST, max_bytes=MAX_MANIFEST,
                   private=True) != manifest:
        raise ProvenanceError("signed claim changed during independent verification")
    return {
        "schema": "skeleton.local-ai.docker.signed-claim-verification.v1",
        "status": "two_independent_signatures_valid_claims_not_physical_or_release_proof",
        "expected_source_head": expected_head,
        "claims_sha256": hashlib.sha256(manifest).hexdigest(),
        "security_public_key_sha256": hashlib.sha256(sec).hexdigest(),
        "release_public_key_sha256": hashlib.sha256(rel).hexdigest(),
        "distinct_external_authorities_verified": True,
        "openssl_ed25519_verified": True,
        "referenced_physical_receipts_independently_checked": False,
        "protected_chat_qualified": False,
        "coherent_database_recovery_qualified": False,
        "device_qualified": False,
        "release_authorized": False,
        "merge_authorized": False,
    }


__all__ = ["verify_signed_release_claims"]
