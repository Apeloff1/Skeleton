"""Offline, non-authoritative WiredTiger and three-store ledger acceptance.

These fixtures never start mongod, load a BSON/WiredTiger parser, access
Docker, or inspect production user records. They reject invented replay,
writer quiescence and coherent recovery authority.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import local_ai_offline_three_store as three
from scripts import local_ai_restored_mongo as mongo

SHA = "a" * 64
ARCHIVE = Path("/not-a-production-archive")
COPY = Path("/separate-restored-private-copy")


def _v1():
    return {
        "schema": three.ledger.SCHEMA,
        "status": "independent_offline_file_evidence_not_coherent_restore",
        "archive_bytes_verified_before_and_after": True,
        "sqlite_structural_integrity_verified": True,
        "sqlite_databases_checked": 3,
        "chroma_role_present": True,
        "chroma_hnsw_file_custody_verified": True,
        "chroma_persistent_segment_files_hashed": 5,
        "aggregate_observation_sha256": "b" * 64,
        **{name: False for name in three._V1_HOLDS},
    }


def _mongo():
    return {
        "schema": mongo.SCHEMA,
        "status": "wiredtiger_static_file_custody_only_not_mongod_recovery",
        "required_catalog_files_verified": 5,
        "hashed_wiredtiger_files": 11,
        "hashed_wiredtiger_bytes": 4096,
        "collection_files_observed": 2,
        "index_files_observed": 1,
        "journal_files_observed": 1,
        "journal_file_bytes_present": True,
        "diagnostic_directory_present": False,
        "aggregate_file_fingerprint_sha256": "c" * 64,
        "independent_cold_archive_verified_twice": True,
        **{name: False for name in three._MONGO_HOLDS},
    }


def _stub(monkeypatch, *, sqlite=None, mongo_receipt=None, mutate_later=False):
    source_receipt = {
        "roles": ["backend_data", "chroma_data", "mongo_config",
                  "mongo_data", "skeleton_data"],
        "receipt_sha256": "d" * 64,
    }
    sqlite = _v1() if sqlite is None else sqlite
    mongo_receipt = _mongo() if mongo_receipt is None else mongo_receipt
    calls = []
    def source(*args):
        calls.append("source")
        receipt = copy.deepcopy(source_receipt)
        if mutate_later and calls.count("source") == 2:
            receipt["receipt_sha256"] = "e" * 64
        return receipt
    def old(source, destination, *, expected_receipt_sha256):
        assert (source, destination, expected_receipt_sha256) == (
            ARCHIVE, COPY, SHA,
        )
        calls.append("sqlite_chroma")
        return copy.deepcopy(sqlite)
    def mongo_check(source, destination, *, expected_receipt_sha256):
        assert (source, destination, expected_receipt_sha256) == (
            ARCHIVE, COPY, SHA,
        )
        calls.append("mongo")
        return copy.deepcopy(mongo_receipt)
    monkeypatch.setattr(three.ledger, "_first", source)
    monkeypatch.setattr(three.ledger, "audit_offline_recovery_evidence", old)
    monkeypatch.setattr(three.mongo, "inspect_restored_mongo", mongo_check)
    return calls


def _run():
    return three.inspect_offline_three_store_evidence(
        ARCHIVE, COPY, expected_receipt_sha256=SHA,
    )


def test_independent_three_store_evidence_is_bounded_without_recovery_claim(
        monkeypatch):
    calls = _stub(monkeypatch)
    report = _run()
    assert calls == ["source", "sqlite_chroma", "mongo", "source"]
    assert report["schema"] == three.SCHEMA
    assert report["status"] == "independent_mongo_sqlite_chroma_file_custody_not_recovery"
    assert report["mongo_wiredtiger_catalog_file_custody_verified"] is True
    assert report["mongo_wiredtiger_files_hashed"] == 11
    assert report["mongo_journal_files_observed"] == 1
    assert report["sqlite_structural_integrity_verified"] is True
    assert report["chroma_hnsw_file_custody_verified"] is True
    assert len(report["aggregate_evidence_sha256"]) == 64
    for name in (
        "mongod_logical_replay_qualified",
        "mongo_majority_journal_durability_qualified",
        "source_writer_quiescence_verified",
        "sqlite_semantic_recovery_qualified",
        "native_chroma_graph_query_qualified",
        "cross_store_transaction_coherence_qualified",
        "application_restore_qualified",
        "protected_jeeves_chat_qualified",
        "release_authorized",
    ):
        assert report[name] is False
    assert "not-a-production" not in str(report)


def test_three_store_observation_digest_is_deterministic(monkeypatch):
    _stub(monkeypatch)
    assert _run() == _run()


def test_archive_provenance_drift_on_last_check_fails(monkeypatch):
    calls = _stub(monkeypatch, mutate_later=True)
    with pytest.raises(three.ThreeStoreEvidenceError, match="changed"):
        _run()
    assert calls == ["source", "sqlite_chroma", "mongo", "source"]


@pytest.mark.parametrize("poison", [
    {"schema": "other"}, {"status": "recovered"},
    {"archive_bytes_verified_before_and_after": False},
    {"physical_source_writers_quiesced": True},
    {"mongo_wiredtiger_logical_recovery_qualified": True},
    {"release_authorized": True},
    {"sqlite_structural_integrity_verified": "yes"},
    {"sqlite_databases_checked": True},
    {"chroma_role_present": "true"},
    {"chroma_persistent_segment_files_hashed": 9},
    {"chroma_hnsw_file_custody_verified": False},
    {"aggregate_observation_sha256": "INVALID"},
    {"raw_sql": "PRIVATE CONTENT"},
])
def test_forged_prior_sqlite_chroma_ledger_denied_before_mongo(
        monkeypatch, poison):
    calls = _stub(monkeypatch, sqlite={**_v1(), **poison})
    with pytest.raises(three.ThreeStoreEvidenceError):
        _run()
    assert calls == ["source", "sqlite_chroma"]


@pytest.mark.parametrize("poison", [
    {"schema": "other"}, {"status": "recovered"},
    {"required_catalog_files_verified": False},
    {"required_catalog_files_verified": 4},
    {"journal_files_observed": True},
    {"journal_file_bytes_present": "yes"},
    {"diagnostic_directory_present": "yes"},
    {"hashed_wiredtiger_files": 4},
    {"hashed_wiredtiger_bytes": 0},
    {"collection_files_observed": 100},
    {"index_files_observed": 100},
    {"journal_files_observed": -1},
    {"mongo_journal_replayed": True},
    {"mongo_logical_consistency_verified": True},
    {"mongod_process_started": True},
    {"release_authorized": True},
    {"aggregate_file_fingerprint_sha256": "INVALID"},
    {"private_mongo_document": "SECRET"},
])
def test_wiredtiger_receipt_cannot_invent_logical_recovery(
        monkeypatch, poison):
    calls = _stub(monkeypatch, mongo_receipt={**_mongo(), **poison})
    with pytest.raises(three.ThreeStoreEvidenceError):
        _run()
    assert calls == ["source", "sqlite_chroma", "mongo"]


def test_empty_sqlite_or_chroma_is_reported_not_promoted(monkeypatch):
    sql = {**_v1(), "sqlite_databases_checked": 0,
           "sqlite_structural_integrity_verified": False,
           "chroma_hnsw_file_custody_verified": False,
           "chroma_persistent_segment_files_hashed": 0}
    _stub(monkeypatch, sqlite=sql)
    report = _run()
    assert report["sqlite_structural_integrity_verified"] is False
    assert report["chroma_hnsw_file_custody_verified"] is False
    assert report["application_restore_qualified"] is False


def test_no_mongo_journal_is_not_replayed(monkeypatch):
    receipt = {**_mongo(), "journal_files_observed": 0,
               "journal_file_bytes_present": False,
               "hashed_wiredtiger_files": 10}
    _stub(monkeypatch, mongo_receipt=receipt)
    report = _run()
    assert report["mongo_journal_files_observed"] == 0
    assert report["mongod_logical_replay_qualified"] is False


def test_invalid_cold_receipt_digest_denied_before_source_access(monkeypatch):
    monkeypatch.setattr(three.ledger, "_first", lambda *args:
                        pytest.fail("invalid hash reached cold source"))
    with pytest.raises(three.ThreeStoreEvidenceError):
        three.inspect_offline_three_store_evidence(
            ARCHIVE, COPY, expected_receipt_sha256="INVALID",
        )


def test_driver_error_redacts_private_mongo_uri(monkeypatch):
    _stub(monkeypatch)
    def fail(*args, **kwargs):
        raise RuntimeError("mongodb://admin:PRIVATE-PASSWORD@real-mongo:27017")
    monkeypatch.setattr(three.mongo, "inspect_restored_mongo", fail)
    with pytest.raises(three.ThreeStoreEvidenceError) as error:
        _run()
    assert "PRIVATE-PASSWORD" not in str(error.value)


def test_real_dummy_wiredtiger_file_envelope_in_composed_ledger(
        tmp_path, monkeypatch):
    """Run the actual descriptor-bound Mongo scanner on private dummy files."""
    from skeleton.testing.test_local_ai_restored_mongo import (
        _fixture as physical_fixture,
    )
    destination, data, calls, receipt = physical_fixture(tmp_path, monkeypatch)
    source = {
        "receipt_sha256": "d" * 64,
        "roles": ["backend_data", "chroma_data", "mongo_config",
                  "mongo_data", "skeleton_data"],
    }
    monkeypatch.setattr(three.ledger, "_first",
                        lambda *args: copy.deepcopy(source))
    monkeypatch.setattr(
        three.ledger, "audit_offline_recovery_evidence",
        lambda *args, **kwargs: _v1(),
    )
    result = three.inspect_offline_three_store_evidence(
        Path("/no-live-backup"), destination,
        expected_receipt_sha256=SHA,
    )
    assert result["mongo_wiredtiger_files_hashed"] >= 5
    assert result["mongo_journal_files_observed"] == 1
    assert result["mongod_logical_replay_qualified"] is False
    assert len(calls) == 2


def test_readonly_ledger_cannot_reach_docker_daemon(monkeypatch):
    _stub(monkeypatch)
    monkeypatch.setattr(three.host, "_run", lambda *a, **kw:
                        pytest.fail("offline three-store observation reached Docker"))
    assert _run()["release_authorized"] is False
