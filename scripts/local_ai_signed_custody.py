#!/usr/bin/env python3
"""Independently double-sign-VERIFY offline three-store *file custody*.

Two externally supplied Ed25519 PUBLIC keys must validate detached signatures
over a canonical, strictly non-authorizing manifest whose evidence SHA is
freshly recalculated against separately restored private archive bytes.

No signing or key generation, no private-key access, no source data writes,
no Docker, no mongod, no native Chroma graph, and NO RELEASE AUTHORITY.
A valid signature authenticates only a file-custody observation; it does not
establish quiesced writers, logical recovery, transaction consistency or
cryptographic provenance of an application release.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from scripts import local_ai_release_attestation as base
from scripts import local_ai_offline_three_store as three
from scripts import local_ai_docker as host

SCHEMA = "skeleton.local-ai.docker.double-signed-offline-custody.v1"
RESULT_SCHEMA = "skeleton.local-ai.docker.offline-custody-signatures-verified.v1"
MANIFEST = "offline-three-store-claims.json"
SIGNATURES = {
    "operator": "operator.ed25519.sig",
    "auditor": "auditor.ed25519.sig",
}
_MAX_MANIFEST = 4096
_MAX_PEM = 4096
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset((
    "schema", "status", "source_head_sha",
    "cold_source_receipt_sha256", "aggregate_evidence_sha256",
    "signer_domains", "mongo_logical_recovery_qualified",
    "sqlite_semantic_recovery_qualified",
    "native_chroma_graph_qualified", "source_writer_quiescence_verified",
    "cross_store_transaction_coherence_qualified",
    "application_restore_qualified", "release_authorized",
))
_FALSE = frozenset((
    "mongo_logical_recovery_qualified",
    "sqlite_semantic_recovery_qualified",
    "native_chroma_graph_qualified",
    "source_writer_quiescence_verified",
    "cross_store_transaction_coherence_qualified",
    "application_restore_qualified", "release_authorized",
))

_PHYSICAL_TRUE = frozenset((
    "cold_source_bytes_reverified_after_each_subgate",
    "mongo_wiredtiger_catalog_file_custody_verified",
))
_PHYSICAL_FALSE = frozenset((
    "mongod_logical_replay_qualified",
    "mongo_majority_journal_durability_qualified",
    "source_writer_quiescence_verified",
    "sqlite_semantic_recovery_qualified",
    "native_chroma_graph_query_qualified",
    "cross_store_transaction_coherence_qualified",
    "application_restore_qualified",
    "protected_jeeves_chat_qualified",
    "release_authorized",
))
_PHYSICAL_FIELDS = frozenset((
    "schema", "status", "mongo_wiredtiger_files_hashed",
    "mongo_journal_files_observed", "sqlite_structural_integrity_verified",
    "sqlite_databases_checked", "chroma_hnsw_file_custody_verified",
    "chroma_persistent_segment_files_hashed", "aggregate_evidence_sha256",
)) | _PHYSICAL_TRUE | _PHYSICAL_FALSE



class SignedCustodyError(host.LocalDockerError):
    """Independent externally signed offline file custody unavailable."""


def _sha(value: object, digits: int) -> str:
    pattern = _HEX40 if digits == 40 else _HEX64
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise SignedCustodyError("independent signed custody digest malformed")
    return value


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SignedCustodyError("duplicate signed custody JSON key")
        result[key] = value
    return result


def _no_nonfinite(value: str) -> None:
    raise SignedCustodyError("signed custody contains nonfinite value")


def _validate_claim(
    raw: bytes, *, source_head_sha: str,
    cold_source_receipt_sha256: str,
) -> dict[str, Any]:
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= _MAX_MANIFEST
        or not raw.endswith(b"\n")
    ):
        raise SignedCustodyError("signed custody manifest size or encoding invalid")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_no_duplicates,
            parse_constant=_no_nonfinite,
        )
        canonical = json.dumps(
            value, sort_keys=True, ensure_ascii=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("ascii") + b"\n"
    except SignedCustodyError:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise SignedCustodyError(
            "signed custody manifest cannot be decoded safely"
        ) from None
    if (
        not isinstance(value, dict)
        or set(value) != _FIELDS
        or raw != canonical
        or value.get("schema") != SCHEMA
        or value.get("status") != "signed_file_custody_not_database_recovery"
        or value.get("source_head_sha") != source_head_sha
        or value.get("cold_source_receipt_sha256") != cold_source_receipt_sha256
        or value.get("signer_domains") != ["operator", "auditor"]
        or any(value.get(key) is not False for key in _FALSE)
    ):
        raise SignedCustodyError("signed custody attempts unsupported recovery authority")
    _sha(value.get("source_head_sha"), 40)
    _sha(value.get("cold_source_receipt_sha256"), 64)
    _sha(value.get("aggregate_evidence_sha256"), 64)
    return value


def _external_key_bytes(folder: Path, key: Path) -> bytes:
    if (
        not isinstance(key, Path) or not key.is_absolute()
        or key == folder or folder in key.parents
        or key == folder / MANIFEST
        or any(path.is_symlink() for path in (key, *key.parents))
    ):
        raise SignedCustodyError("signed custody public key must be independent")
    try:
        data = base._owner_file(key, max_bytes=_MAX_PEM, private=False)
    except Exception:
        raise SignedCustodyError(
            "independent external public key unavailable"
        ) from None
    if (
        not data.startswith(b"-----BEGIN PUBLIC KEY-----\n")
        or not data.rstrip().endswith(b"-----END PUBLIC KEY-----")
        or b"PRIVATE" in data
    ):
        raise SignedCustodyError("externally pinned Ed25519 public key invalid")
    return data


def _private_file(path: Path, *, max_bytes: int) -> bytes:
    try:
        return base._owner_file(path, max_bytes=max_bytes, private=True)
    except Exception:
        raise SignedCustodyError("private signed custody source unreadable") from None


def verify_double_signed_offline_custody(
    claims_directory: Path, operator_public_key: Path, auditor_public_key: Path,
    source: Path, destination: Path, *,
    expected_source_head_sha: str, expected_receipt_sha256: str,
) -> dict[str, object]:
    """Read-only external signature verification bound to a fresh v2 ledger."""
    head = _sha(expected_source_head_sha, 40)
    cold = _sha(expected_receipt_sha256, 64)
    try:
        folder = base._private_dir(claims_directory)
    except Exception:
        raise SignedCustodyError("signed custody evidence directory invalid") from None
    if {item.name for item in folder.iterdir()} != (
        {MANIFEST} | set(SIGNATURES.values())
    ):
        raise SignedCustodyError("signed custody evidence contains untrusted members")

    operator_key = _external_key_bytes(folder, operator_public_key)
    auditor_key = _external_key_bytes(folder, auditor_public_key)
    if (
        operator_public_key == auditor_public_key
        or operator_key == auditor_key
        or hashlib.sha256(operator_key).digest()
           == hashlib.sha256(auditor_key).digest()
    ):
        raise SignedCustodyError("two genuinely independent public keys required")

    manifest = _private_file(folder / MANIFEST, max_bytes=_MAX_MANIFEST)
    claimed = _validate_claim(
        manifest, source_head_sha=head, cold_source_receipt_sha256=cold,
    )
    signatures = {}
    for role, filename in SIGNATURES.items():
        signature = _private_file(folder / filename, max_bytes=64)
        if len(signature) != 64:
            raise SignedCustodyError("Ed25519 signature size invalid")
        signatures[role] = signature

    try:
        physical = three.inspect_offline_three_store_evidence(
            source, destination, expected_receipt_sha256=cold,
        )
    except Exception:
        raise SignedCustodyError(
            "independently recalculated three-store file custody unavailable"
        ) from None
    if (
        not isinstance(physical, dict)
        or set(physical) != _PHYSICAL_FIELDS
        or any(physical.get(k) is not True for k in _PHYSICAL_TRUE)
        or any(physical.get(k) is not False for k in _PHYSICAL_FALSE)
        or type(physical.get("sqlite_structural_integrity_verified")) is not bool
        or type(physical.get("chroma_hnsw_file_custody_verified")) is not bool
        or any(type(physical.get(k)) is not int for k in (
            "mongo_wiredtiger_files_hashed",
            "mongo_journal_files_observed",
            "sqlite_databases_checked",
            "chroma_persistent_segment_files_hashed",
        ))
        or physical["mongo_wiredtiger_files_hashed"] < 5
        or not 0 <= physical["sqlite_databases_checked"] <= 32
        or physical["sqlite_structural_integrity_verified"] is not (
            physical["sqlite_databases_checked"] > 0
        )
        or physical["chroma_hnsw_file_custody_verified"] is not (
            physical["chroma_persistent_segment_files_hashed"] > 0
        )
        or physical.get("schema") != three.SCHEMA
        or physical.get("status") !=
           "independent_mongo_sqlite_chroma_file_custody_not_recovery"
        or physical.get("release_authorized") is not False
        or physical.get("application_restore_qualified") is not False
        or physical.get("mongod_logical_replay_qualified") is not False
        or physical.get("cross_store_transaction_coherence_qualified") is not False
        or physical.get("aggregate_evidence_sha256") !=
           claimed["aggregate_evidence_sha256"]
    ):
        raise SignedCustodyError("signed claim disagrees with fresh offline bytes")

    for role, key in (
        ("operator", operator_public_key), ("auditor", auditor_public_key)
    ):
        try:
            process = subprocess.run(
                [
                    "openssl", "pkeyutl", "-verify", "-pubin",
                    "-inkey", str(key), "-rawin",
                    "-in", str(folder / MANIFEST),
                    "-sigfile", str(folder / SIGNATURES[role]),
                ],
                text=True, capture_output=True, check=False, timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise SignedCustodyError(
                "independent Ed25519 verifier unavailable"
            ) from None
        if process.returncode != 0:
            raise SignedCustodyError(
                "independent Ed25519 custody signature invalid"
            )

    if (
        _private_file(folder / MANIFEST, max_bytes=_MAX_MANIFEST) != manifest
        or any(
            _private_file(folder / SIGNATURES[role], max_bytes=64) != value
            for role, value in signatures.items()
        )
        or _external_key_bytes(folder, operator_public_key) != operator_key
        or _external_key_bytes(folder, auditor_public_key) != auditor_key
    ):
        raise SignedCustodyError("signed custody manifest or authority changed")

    # Final physical byte recomputation closes the verification interval.
    try:
        repeated = three.inspect_offline_three_store_evidence(
            source, destination, expected_receipt_sha256=cold,
        )
    except Exception:
        raise SignedCustodyError("signed evidence source changed after verification") from None
    if repeated != physical:
        raise SignedCustodyError(
            "source/restored bytes drifted after signature verification"
        )
    return {
        "schema": RESULT_SCHEMA,
        "status": "independent_double_signed_file_custody_not_recovery",
        "source_head_sha": head,
        "signed_claim_sha256": hashlib.sha256(manifest).hexdigest(),
        "offline_file_evidence_sha256": claimed["aggregate_evidence_sha256"],
        "operator_public_key_sha256": hashlib.sha256(operator_key).hexdigest(),
        "auditor_public_key_sha256": hashlib.sha256(auditor_key).hexdigest(),
        "distinct_external_authorities_verified": True,
        "fresh_three_store_file_evidence_rechecked": True,
        "openssl_ed25519_signatures_verified": True,
        "private_keys_accessed": False,
        "source_archive_modified": False,
        "database_process_started": False,
        "mongo_logical_recovery_qualified": False,
        "cross_store_transaction_coherence_qualified": False,
        "application_restore_qualified": False,
        "protected_jeeves_chat_qualified": False,
        "release_authorized": False,
        "merge_authorized": False,
    }


__all__ = [
    "SignedCustodyError", "verify_double_signed_offline_custody",
]
