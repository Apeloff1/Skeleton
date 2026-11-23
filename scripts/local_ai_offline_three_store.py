"""Versioned three-store offline recovery *evidence*, never recovery authority.

This v2 ledger augments the existing read-only SQLite/Chroma v1 ledger
with an independently scanned Mongo WiredTiger catalog/data/journal byte
envelope. It does not start mongod, recover Mongo pages, load Chroma,
play transactions, pause live writers, or attest an atomic three-store
snapshot. All databases are separately observed read-only on a new
private copy after complete receipt revalidation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from scripts import local_ai_data_rehydration as restore
from scripts import local_ai_offline_recovery_ledger as ledger
from scripts import local_ai_restored_mongo as mongo
from scripts import local_ai_docker as host

SCHEMA = "skeleton.local-ai.docker.offline-three-store-evidence-ledger.v2"
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_V1_FIELDS = frozenset((
    "schema", "status", "archive_bytes_verified_before_and_after",
    "sqlite_structural_integrity_verified", "sqlite_databases_checked",
    "chroma_role_present", "chroma_hnsw_file_custody_verified",
    "chroma_persistent_segment_files_hashed",
    "aggregate_observation_sha256",
    "physical_source_writers_quiesced",
    "mongo_wiredtiger_logical_recovery_qualified",
    "sqlite_application_semantics_qualified",
    "chroma_native_vector_query_qualified",
    "cross_store_transaction_coherence_qualified",
    "database_application_restore_qualified",
    "protected_jeeves_chat_qualified", "release_authorized",
))
_MONGO_FIELDS = frozenset((
    "schema", "status", "required_catalog_files_verified",
    "hashed_wiredtiger_files", "hashed_wiredtiger_bytes",
    "collection_files_observed", "index_files_observed",
    "journal_files_observed", "journal_file_bytes_present",
    "diagnostic_directory_present",
    "aggregate_file_fingerprint_sha256",
    "independent_cold_archive_verified_twice",
    "wiredtiger_page_parser_executed", "mongod_process_started",
    "mongo_journal_replayed", "mongo_logical_consistency_verified",
    "external_writer_quiescence_verified",
    "mongo_application_transactions_recovered",
    "sqlite_chroma_alignment_verified", "cross_store_snapshot_atomic",
    "application_restore_qualified", "protected_jeeves_chat_qualified",
    "release_authorized",
))
_V1_HOLDS = frozenset((
    "physical_source_writers_quiesced",
    "mongo_wiredtiger_logical_recovery_qualified",
    "sqlite_application_semantics_qualified",
    "chroma_native_vector_query_qualified",
    "cross_store_transaction_coherence_qualified",
    "database_application_restore_qualified",
    "protected_jeeves_chat_qualified", "release_authorized",
))
_MONGO_HOLDS = frozenset((
    "wiredtiger_page_parser_executed", "mongod_process_started",
    "mongo_journal_replayed", "mongo_logical_consistency_verified",
    "external_writer_quiescence_verified",
    "mongo_application_transactions_recovered",
    "sqlite_chroma_alignment_verified",
    "cross_store_snapshot_atomic", "application_restore_qualified",
    "protected_jeeves_chat_qualified", "release_authorized",
))


class ThreeStoreEvidenceError(host.LocalDockerError):
    """Independent three-store offline file custody is not established."""


def _sha(value: object) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ThreeStoreEvidenceError("three-store evidence SHA invalid")
    return value


def _v1(raw: object) -> dict[str, Any]:
    if (
        not isinstance(raw, dict)
        or set(raw) != _V1_FIELDS
        or raw.get("schema") != ledger.SCHEMA
        or raw.get("status") !=
           "independent_offline_file_evidence_not_coherent_restore"
        or raw.get("archive_bytes_verified_before_and_after") is not True
        or any(raw.get(k) is not False for k in _V1_HOLDS)
        or type(raw.get("sqlite_structural_integrity_verified")) is not bool
        or type(raw.get("chroma_role_present")) is not bool
        or type(raw.get("chroma_hnsw_file_custody_verified")) is not bool
        or type(raw.get("sqlite_databases_checked")) is not int
        or not 0 <= raw["sqlite_databases_checked"] <= 32
        or type(raw.get("chroma_persistent_segment_files_hashed")) is not int
        or not 0 <= raw["chroma_persistent_segment_files_hashed"] <= 128 * 5
        or raw["chroma_hnsw_file_custody_verified"] is not
           (raw["chroma_persistent_segment_files_hashed"] > 0)
        or (raw["chroma_hnsw_file_custody_verified"]
            and not raw["chroma_role_present"])
        or raw["sqlite_structural_integrity_verified"] is not
           (raw["sqlite_databases_checked"] > 0)
    ):
        raise ThreeStoreEvidenceError("SQLite/Chroma ledger scope or counts invalid")
    _sha(raw.get("aggregate_observation_sha256"))
    return raw


def _mongo(raw: object) -> dict[str, Any]:
    if (
        not isinstance(raw, dict)
        or set(raw) != _MONGO_FIELDS
        or raw.get("schema") != mongo.SCHEMA
        or raw.get("status") !=
           "wiredtiger_static_file_custody_only_not_mongod_recovery"
        or raw.get("required_catalog_files_verified") != 5
        or type(raw.get("required_catalog_files_verified")) is not int
        or raw.get("independent_cold_archive_verified_twice") is not True
        or any(raw.get(k) is not False for k in _MONGO_HOLDS)
        or type(raw.get("journal_file_bytes_present")) is not bool
        or type(raw.get("diagnostic_directory_present")) is not bool
    ):
        raise ThreeStoreEvidenceError("Mongo WiredTiger receipt claimed invalid authority")
    counters = (
        "hashed_wiredtiger_files", "hashed_wiredtiger_bytes",
        "collection_files_observed", "index_files_observed",
        "journal_files_observed",
    )
    if any(type(raw.get(k)) is not int for k in counters):
        raise ThreeStoreEvidenceError("Mongo file receipt counter not an integer")
    if (
        not 5 <= raw["hashed_wiredtiger_files"] <= 100_000 + 8192
        or not 0 < raw["hashed_wiredtiger_bytes"] <= 32 * 1024 ** 4
        or not 0 <= raw["collection_files_observed"]
                 <= raw["hashed_wiredtiger_files"]
        or not 0 <= raw["index_files_observed"]
                 <= raw["hashed_wiredtiger_files"]
        or not 0 <= raw["journal_files_observed"] <= 8192
        or raw["journal_file_bytes_present"] is not
            (raw["journal_files_observed"] > 0)
        or raw["collection_files_observed"] + raw["index_files_observed"]
           + raw["journal_files_observed"] + 5
           > raw["hashed_wiredtiger_files"]
    ):
        raise ThreeStoreEvidenceError("Mongo file envelope tallies inconsistent")
    _sha(raw.get("aggregate_file_fingerprint_sha256"))
    return raw


def inspect_offline_three_store_evidence(
    source: Path, destination: Path, *,
    expected_receipt_sha256: str,
) -> dict[str, object]:
    """Only combine independently qualified physical cold file evidence."""
    source_sha = _sha(expected_receipt_sha256)
    try:
        initial = ledger._first(source, destination, source_sha)
        sqlite_chroma = _v1(ledger.audit_offline_recovery_evidence(
            source, destination,
            expected_receipt_sha256=source_sha,
        ))
        wiredtiger = _mongo(mongo.inspect_restored_mongo(
            source, destination,
            expected_receipt_sha256=source_sha,
        ))
        after = ledger._first(source, destination, source_sha)
    except ThreeStoreEvidenceError:
        raise
    except Exception:
        raise ThreeStoreEvidenceError(
            "independent offline three-store file source unavailable"
        ) from None
    if after != initial:
        raise ThreeStoreEvidenceError(
            "cold source or restored bytes changed between three-store checks"
        )
    # This observation digest has NO signing or release authority.
    facts = {
        "cold_archive_sha256": source_sha,
        "restored_receipt_sha256": initial["receipt_sha256"],
        "sqlite_chroma_ledger_sha256":
            sqlite_chroma["aggregate_observation_sha256"],
        "wiredtiger_envelope_sha256":
            wiredtiger["aggregate_file_fingerprint_sha256"],
        "mongo_catalog_files": wiredtiger["hashed_wiredtiger_files"],
        "mongo_journal_files": wiredtiger["journal_files_observed"],
        "sqlite_databases_checked":
            sqlite_chroma["sqlite_databases_checked"],
        "chroma_hnsw_files_hashed":
            sqlite_chroma["chroma_persistent_segment_files_hashed"],
    }
    canonical = json.dumps(
        facts, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("ascii")
    fingerprint = hashlib.sha256(
        b"skeleton.offline-three-store-evidence-ledger.v2\x00" + canonical
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "status": "independent_mongo_sqlite_chroma_file_custody_not_recovery",
        "cold_source_bytes_reverified_after_each_subgate": True,
        "mongo_wiredtiger_catalog_file_custody_verified": True,
        "mongo_wiredtiger_files_hashed":
            wiredtiger["hashed_wiredtiger_files"],
        "mongo_journal_files_observed":
            wiredtiger["journal_files_observed"],
        "sqlite_structural_integrity_verified":
            sqlite_chroma["sqlite_structural_integrity_verified"],
        "sqlite_databases_checked":
            sqlite_chroma["sqlite_databases_checked"],
        "chroma_hnsw_file_custody_verified":
            sqlite_chroma["chroma_hnsw_file_custody_verified"],
        "chroma_persistent_segment_files_hashed":
            sqlite_chroma["chroma_persistent_segment_files_hashed"],
        "aggregate_evidence_sha256": fingerprint,
        "mongod_logical_replay_qualified": False,
        "mongo_majority_journal_durability_qualified": False,
        "source_writer_quiescence_verified": False,
        "sqlite_semantic_recovery_qualified": False,
        "native_chroma_graph_query_qualified": False,
        "cross_store_transaction_coherence_qualified": False,
        "application_restore_qualified": False,
        "protected_jeeves_chat_qualified": False,
        "release_authorized": False,
    }


__all__ = [
    "ThreeStoreEvidenceError", "inspect_offline_three_store_evidence",
]
