#!/usr/bin/env python3
"""Read-only cross-store *evidence ledger*, never cross-store recovery.

Combine three separately revalidated offline receipts:
(1) original cold archive and new byte-rehydration custody;
(2) actual SQLite structural/foreign-key integrity;
(3) optional historical local Chroma HNSW segment-file custody.

No production writer pause, Mongo WiredTiger logical replay, native Chroma
graph load, atomic snapshot, application replay or release is implied.
No data is written to source, destination or Docker. This ledger is an
unsigned deterministic observation digest, not release provenance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from scripts import local_ai_data_rehydration as restored
from scripts import local_ai_restored_sqlite as sqlite
from scripts import local_ai_restored_chroma as chroma
from scripts import local_ai_docker as host

SCHEMA = "skeleton.local-ai.docker.offline-recovery-evidence-ledger.v1"
_EXPECTED_ROLES = frozenset((
    "backend_data", "mongo_config", "mongo_data", "skeleton_data",
))
_OPT_CHROMA = "chroma_data"
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_EXACT_RESTORED = frozenset((
    "schema", "status", "source_receipt_file_sha256", "roles", "volumes",
    "total_files", "total_bytes", "external_volumes_created",
    "source_archive_mutated", "docker_daemon_used",
    "database_process_started", "sqlite_consistency_verified",
    "mongo_consistency_verified", "chroma_consistency_verified",
    "cross_store_snapshot_atomic", "application_restore_qualified",
    "protected_chat_qualified", "release_qualified",
    "receipt_sha256",
))
_RESTORED_FALSE = frozenset((
    "external_volumes_created", "source_archive_mutated",
    "docker_daemon_used", "database_process_started",
    "sqlite_consistency_verified", "mongo_consistency_verified",
    "chroma_consistency_verified", "cross_store_snapshot_atomic",
    "application_restore_qualified", "protected_chat_qualified",
    "release_qualified",
))
_SQLITE_FALSE = frozenset((
    "sqlite_wal_or_journal_accepted", "source_archive_modified",
    "restored_bytes_modified", "docker_daemon_used",
    "mongo_consistency_verified", "chroma_consistency_verified",
    "cross_store_snapshot_atomic", "application_restore_qualified",
    "protected_jeeves_chat_qualified", "release_authorized",
))
_CHROMA_FALSE = frozenset((
    "pickle_deserialized", "hnsw_graph_load_qualified",
    "chroma_logical_replay_qualified", "database_documents_read",
    "source_archive_modified", "restored_bytes_modified",
    "mongo_consistency_verified", "cross_store_snapshot_atomic",
    "application_restore_qualified", "protected_jeeves_chat_qualified",
    "release_authorized",
))
_SQLITE_FIELDS = frozenset((
    "schema", "status", "sqlite_databases_detected",
    "sqlite_databases_integrity_checked", "sqlite_total_bytes",
    "all_detected_sqlite_integrity_ok",
)) | _SQLITE_FALSE
_CHROMA_FIELDS = frozenset((
    "schema", "status", "persistent_vector_segments",
    "all_index_files_present_and_hashed",
)) | _CHROMA_FALSE
_CHROMA_INDEX_FIELDS = frozenset((
    "hashed_index_files", "total_binary_index_bytes",
    "catalog_and_segment_file_identity_verified",
    "aggregate_fingerprint_sha256",
))


class OfflineRecoveryLedgerError(host.LocalDockerError):
    """Independent offline recovery evidence is incomplete or misleading."""


def _hash(value: object, field: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise OfflineRecoveryLedgerError("offline recovery digest invalid")
    return value


def _first(source: Path, destination: Path, sha256: str) -> dict[str, Any]:
    try:
        report = restored.verify_rehydration(
            source, destination, expected_receipt_sha256=sha256,
        )
    except Exception:
        raise OfflineRecoveryLedgerError(
            "independent application cold archive custody unavailable"
        ) from None
    if (
        not isinstance(report, dict)
        or set(report) != _EXACT_RESTORED
        or report.get("schema") != restored.SCHEMA
        or report.get("status") != "all_cold_archive_files_rehydrated_not_database_restored"
        or report.get("source_receipt_file_sha256") != sha256
        or any(report.get(key) is not False for key in _RESTORED_FALSE)
        or type(report.get("total_files")) is not int
        or type(report.get("total_bytes")) is not int
        or not 0 <= report["total_files"] <= 5_000_000 * 5
        or not 0 <= report["total_bytes"] <= 32 * (1024 ** 4) * 5
    ):
        raise OfflineRecoveryLedgerError(
            "cold byte-only evidence attempted to escalate restore authority"
        )
    roles = report.get("roles")
    if (
        not isinstance(roles, list)
        or roles != sorted(roles)
        or any(type(role) is not str for role in roles)
        or len(set(roles)) != len(roles)
        or set(roles) not in (_EXPECTED_ROLES, _EXPECTED_ROLES | {_OPT_CHROMA})
        or not isinstance(report.get("volumes"), list)
        or len(report["volumes"]) != len(roles)
        or not isinstance(report.get("receipt_sha256"), str)
        or _HEX.fullmatch(report["receipt_sha256"]) is None
    ):
        raise OfflineRecoveryLedgerError("offline restored role/receipt inventory invalid")
    file_count = 0
    byte_count = 0
    for role, row in zip(roles, report["volumes"]):
        if (
            not isinstance(row, dict)
            or set(row) != {
                "role", "files", "bytes",
                "source_manifest_sha256", "independent_destination_rehash",
            }
            or row.get("role") != role
            or row.get("independent_destination_rehash") is not True
            or type(row.get("files")) is not int
            or type(row.get("bytes")) is not int
            or not 0 <= row["files"] <= 5_000_000
            or not 0 <= row["bytes"] <= 32 * (1024 ** 4)
        ):
            raise OfflineRecoveryLedgerError(
                "offline per-volume receipt cannot establish canonical byte custody"
            )
        _hash(row.get("source_manifest_sha256"), "volume manifest")
        file_count += row["files"]
        byte_count += row["bytes"]
    if file_count != report["total_files"] or byte_count != report["total_bytes"]:
        raise OfflineRecoveryLedgerError("restored volume inventory totals differ")
    return report


def _sqlite_receipt(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema") != sqlite.SCHEMA:
        raise OfflineRecoveryLedgerError("restored SQLite integrity evidence missing")
    if set(raw) not in (_SQLITE_FIELDS, _SQLITE_FIELDS | {"aggregate_content_fingerprint_sha256"}):
        raise OfflineRecoveryLedgerError("unexpected SQLite integrity receipt fields")
    if any(raw.get(field) is not False for field in _SQLITE_FALSE):
        raise OfflineRecoveryLedgerError("SQLite proof exceeded byte-only authority")
    present = raw.get("sqlite_databases_detected")
    checked = raw.get("sqlite_databases_integrity_checked")
    size = raw.get("sqlite_total_bytes")
    if (
        type(present) is not int or type(checked) is not int
        or type(size) is not int or not 0 <= size <= 32 * (2 * 1024 ** 3)
        or not 0 <= checked == present <= 32
    ):
        raise OfflineRecoveryLedgerError("restored SQLite source counts invalid")
    if present == 0:
        if (raw.get("status") != "no_restored_sqlite_candidates_not_database_qualified"
                or raw.get("all_detected_sqlite_integrity_ok") is not False
                or set(raw) != _SQLITE_FIELDS):
            raise OfflineRecoveryLedgerError("empty SQLite evidence claimed integrity")
    elif (
        raw.get("status") != "restored_sqlite_integrity_only_not_application_recovery"
        or raw.get("all_detected_sqlite_integrity_ok") is not True
    ):
        raise OfflineRecoveryLedgerError("SQLite integrity not independently confirmed")
    if present > 0:
        if set(raw) != _SQLITE_FIELDS | {"aggregate_content_fingerprint_sha256"}:
            raise OfflineRecoveryLedgerError("SQLite digest receipt fields incomplete")
        _hash(raw.get("aggregate_content_fingerprint_sha256"), "sqlite fingerprint")
    return raw


def _chroma_receipt(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema") != chroma.SCHEMA:
        raise OfflineRecoveryLedgerError("restored Chroma source receipt invalid")
    if set(raw) not in (_CHROMA_FIELDS, _CHROMA_FIELDS | _CHROMA_INDEX_FIELDS):
        raise OfflineRecoveryLedgerError("unexpected Chroma index receipt fields")
    for field in _CHROMA_FALSE:
        if raw.get(field) is not False:
            raise OfflineRecoveryLedgerError("restored Chroma claimed native graph recovery")
    n = raw.get("persistent_vector_segments")
    if type(n) is not int or not 0 <= n <= chroma._MAX_SEGMENTS:
        raise OfflineRecoveryLedgerError("Chroma vector segment count invalid")
    if n == 0:
        if (
            raw.get("status") != "chroma_metadata_present_no_persistent_hnsw_segments"
            or raw.get("all_index_files_present_and_hashed") is not False
            or set(raw) != _CHROMA_FIELDS
        ):
            raise OfflineRecoveryLedgerError("empty Chroma vector graph claimed qualified")
    else:
        if (
            raw.get("status") != "read_only_legacy_hnsw_file_custody_not_chroma_recovery"
            or set(raw) != _CHROMA_FIELDS | _CHROMA_INDEX_FIELDS
            or raw.get("all_index_files_present_and_hashed") is not True
            or raw.get("catalog_and_segment_file_identity_verified") is not True
            or type(raw.get("hashed_index_files")) is not int
            or raw["hashed_index_files"] != n * 5
            or type(raw.get("total_binary_index_bytes")) is not int
            or not 0 < raw["total_binary_index_bytes"] <= chroma._MAX_TOTAL_BYTES
        ):
            raise OfflineRecoveryLedgerError("Chroma file envelope proof incomplete")
        _hash(raw.get("aggregate_fingerprint_sha256"), "Chroma fingerprint")
    return raw


def audit_offline_recovery_evidence(
    source: Path, destination: Path, *,
    expected_receipt_sha256: str,
) -> dict[str, object]:
    """Bind independent restore, SQLite and Chroma bytes without mutation."""
    digest = _hash(expected_receipt_sha256, "cold source sha")
    initial = _first(source, destination, digest)
    try:
        checked_sqlite = _sqlite_receipt(sqlite.verify_restored_sqlite(
            source, destination, expected_receipt_sha256=digest,
        ))
        has_chroma = _OPT_CHROMA in initial["roles"]
        checked_chroma = (
            _chroma_receipt(chroma.inspect_restored_chroma(
                source, destination, expected_receipt_sha256=digest,
            ))
            if has_chroma else None
        )
    except OfflineRecoveryLedgerError:
        raise
    except Exception:
        raise OfflineRecoveryLedgerError(
            "independent offline source integrity subgate denied"
        ) from None
    repeated = _first(source, destination, digest)
    if repeated != initial:
        raise OfflineRecoveryLedgerError(
            "offline source/archive receipts changed between independent checks"
        )
    sqlite_count = checked_sqlite["sqlite_databases_integrity_checked"]
    chroma_count = (
        checked_chroma["persistent_vector_segments"]
        if checked_chroma is not None else 0
    )
    sqlite_digest = (
        checked_sqlite["aggregate_content_fingerprint_sha256"]
        if sqlite_count else None
    )
    chroma_digest = (
        checked_chroma["aggregate_fingerprint_sha256"]
        if checked_chroma and chroma_count else None
    )
    envelope = {
        "cold_archive_receipt_file_sha256": digest,
        "rehydration_receipt_sha256": initial["receipt_sha256"],
        "sqlite_integrity_digest": sqlite_digest,
        "chroma_hnsw_file_digest": chroma_digest,
        "sqlite_integrity_count": sqlite_count,
        "chroma_binary_segment_count": chroma_count,
        "chroma_role_present": has_chroma,
    }
    canonical = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("ascii")
    evidence_digest = hashlib.sha256(
        b"skeleton.offline-recovery-evidence-ledger.v1\x00" + canonical
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "status": "independent_offline_file_evidence_not_coherent_restore",
        "archive_bytes_verified_before_and_after": True,
        "sqlite_structural_integrity_verified": sqlite_count > 0,
        "sqlite_databases_checked": sqlite_count,
        "chroma_role_present": has_chroma,
        "chroma_hnsw_file_custody_verified": bool(chroma_count),
        "chroma_persistent_segment_files_hashed": chroma_count * 5,
        "aggregate_observation_sha256": evidence_digest,
        "physical_source_writers_quiesced": False,
        "mongo_wiredtiger_logical_recovery_qualified": False,
        "sqlite_application_semantics_qualified": False,
        "chroma_native_vector_query_qualified": False,
        "cross_store_transaction_coherence_qualified": False,
        "database_application_restore_qualified": False,
        "protected_jeeves_chat_qualified": False,
        "release_authorized": False,
    }


__all__ = ["OfflineRecoveryLedgerError", "audit_offline_recovery_evidence"]