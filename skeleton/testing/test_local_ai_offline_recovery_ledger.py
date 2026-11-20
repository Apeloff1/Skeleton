"""Independent offline SQLite+Chroma evidence composition and hostile receipts.

Only disposable synthetic SQLite/index files are created. Cold-source
verification is mocked to its exact structured receipt at the orchestrator
boundary; actual SQLite/Chroma private-file probes remain real in one
end-to-end fixture. No Docker daemon, production volume, pickle loading,
native HNSW execution, user data or release authority.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import local_ai_offline_recovery_ledger as ledger
from skeleton.testing.test_local_ai_restored_chroma import (
    _fixture as chroma_fixture,
)
from skeleton.testing.test_local_ai_restored_sqlite import _database


SOURCE = Path("/no-production-archive")
SHA = "a" * 64
ROLES = ["backend_data", "chroma_data", "mongo_config", "mongo_data",
         "skeleton_data"]


def _restored(roles=ROLES):
    return {
        "schema": ledger.restored.SCHEMA,
        "status": "all_cold_archive_files_rehydrated_not_database_restored",
        "source_receipt_file_sha256": SHA,
        "roles": list(roles),
        "volumes": [{"role": role} for role in roles],
        "total_files": 11,
        "total_bytes": 123456,
        "external_volumes_created": False,
        "source_archive_mutated": False,
        "docker_daemon_used": False,
        "database_process_started": False,
        "sqlite_consistency_verified": False,
        "mongo_consistency_verified": False,
        "chroma_consistency_verified": False,
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
        "protected_chat_qualified": False,
        "release_qualified": False,
        "receipt_sha256": "b" * 64,
    }


def _sqlite_success():
    return {
        "schema": ledger.sqlite.SCHEMA,
        "status": "restored_sqlite_integrity_only_not_application_recovery",
        "sqlite_databases_detected": 3,
        "sqlite_databases_integrity_checked": 3,
        "sqlite_total_bytes": 4096,
        "aggregate_content_fingerprint_sha256": "c" * 64,
        "all_detected_sqlite_integrity_ok": True,
        **{key: False for key in ledger._SQLITE_FALSE},
    }


def _chroma_success():
    return {
        "schema": ledger.chroma.SCHEMA,
        "status": "read_only_legacy_hnsw_file_custody_not_chroma_recovery",
        "persistent_vector_segments": 1,
        "hashed_index_files": 5,
        "total_binary_index_bytes": 1234,
        "catalog_and_segment_file_identity_verified": True,
        "all_index_files_present_and_hashed": True,
        "aggregate_fingerprint_sha256": "d" * 64,
        **{key: False for key in ledger._CHROMA_FALSE},
    }


def _mock(monkeypatch, *, archive=None, sqlite_receipt=None,
          chroma_receipt=None, change_final=False):
    archive = _restored() if archive is None else archive
    sql = _sqlite_success() if sqlite_receipt is None else sqlite_receipt
    graph = _chroma_success() if chroma_receipt is None else chroma_receipt
    calls = []
    def source_check(source, destination, *, expected_receipt_sha256):
        calls.append("source")
        assert expected_receipt_sha256 == SHA
        result = copy.deepcopy(archive)
        if change_final and calls.count("source") == 2:
            result["receipt_sha256"] = "e" * 64
        return result
    def sql_check(source, destination, *, expected_receipt_sha256):
        calls.append("sqlite")
        assert expected_receipt_sha256 == SHA
        return copy.deepcopy(sql)
    def chroma_check(source, destination, *, expected_receipt_sha256):
        calls.append("chroma")
        assert expected_receipt_sha256 == SHA
        return copy.deepcopy(graph)
    monkeypatch.setattr(ledger.restored, "verify_rehydration", source_check)
    monkeypatch.setattr(ledger.sqlite, "verify_restored_sqlite", sql_check)
    monkeypatch.setattr(ledger.chroma, "inspect_restored_chroma", chroma_check)
    return calls


def _run():
    return ledger.audit_offline_recovery_evidence(
        SOURCE, Path("/new-private-copy"), expected_receipt_sha256=SHA,
    )


def test_proofs_are_sequential_independent_and_not_cross_store_restore(
        monkeypatch):
    calls = _mock(monkeypatch)
    result = _run()
    assert calls == ["source", "sqlite", "chroma", "source"]
    assert result["schema"] == ledger.SCHEMA
    assert result["archive_bytes_verified_before_and_after"] is True
    assert result["sqlite_structural_integrity_verified"] is True
    assert result["sqlite_databases_checked"] == 3
    assert result["chroma_role_present"] is True
    assert result["chroma_hnsw_file_custody_verified"] is True
    assert result["chroma_persistent_segment_files_hashed"] == 5
    assert len(result["aggregate_observation_sha256"]) == 64
    for blocked in (
        "physical_source_writers_quiesced", "mongo_wiredtiger_logical_recovery_qualified",
        "sqlite_application_semantics_qualified", "chroma_native_vector_query_qualified",
        "cross_store_transaction_coherence_qualified",
        "database_application_restore_qualified",
        "protected_jeeves_chat_qualified", "release_authorized",
    ):
        assert result[blocked] is False
    assert "no-production" not in str(result)
    assert "new-private-copy" not in str(result)


def test_same_offline_observation_is_deterministic(monkeypatch):
    calls = _mock(monkeypatch)
    first, second = _run(), _run()
    assert first == second
    assert len(calls) == 8


def test_archive_recheck_detects_drift_after_sqlite_chroma_subgates(monkeypatch):
    calls = _mock(monkeypatch, change_final=True)
    with pytest.raises(ledger.OfflineRecoveryLedgerError, match="changed"):
        _run()
    assert calls == ["source", "sqlite", "chroma", "source"]


@pytest.mark.parametrize("patch", [
    {"source_archive_mutated": True},
    {"sqlite_consistency_verified": True},
    {"application_restore_qualified": True},
    {"release_qualified": True},
    {"schema": "forged"},
    {"status": "fully_recovered"},
    {"roles": ["backend_data", "skeleton_data"]},
    {"source_receipt_file_sha256": "c" * 64},
    {"receipt_sha256": "NOTHEX"},
    {"extra_private_dump": "mongodb://secret"},
    {"total_bytes": True},
])
def test_forged_archive_authority_denied_before_any_subgate(
        monkeypatch, patch):
    proof = {**_restored(), **patch}
    calls = _mock(monkeypatch, archive=proof)
    with pytest.raises(ledger.OfflineRecoveryLedgerError):
        _run()
    assert calls == ["source"]


@pytest.mark.parametrize("patch", [
    {"schema": "forged"},
    {"sqlite_databases_detected": True},
    {"sqlite_databases_integrity_checked": 0},
    {"sqlite_total_bytes": -1},
    {"all_detected_sqlite_integrity_ok": False},
    {"release_authorized": True},
    {"cross_store_snapshot_atomic": True},
    {"aggregate_content_fingerprint_sha256": "NOTHEX"},
])
def test_forged_sqlite_subgate_fails_before_chroma(
        monkeypatch, patch):
    calls = _mock(monkeypatch, sqlite_receipt={**_sqlite_success(), **patch})
    with pytest.raises(ledger.OfflineRecoveryLedgerError):
        _run()
    assert calls == ["source", "sqlite"]


@pytest.mark.parametrize("patch", [
    {"schema": "forged"},
    {"status": "restored"},
    {"persistent_vector_segments": True},
    {"hashed_index_files": 4},
    {"total_binary_index_bytes": -1},
    {"pickle_deserialized": True},
    {"hnsw_graph_load_qualified": True},
    {"chroma_logical_replay_qualified": True},
    {"aggregate_fingerprint_sha256": "NOTHEX"},
    {"release_authorized": True},
])
def test_forged_chroma_graph_custody_or_authority_denied(
        monkeypatch, patch):
    calls = _mock(monkeypatch, chroma_receipt={**_chroma_success(), **patch})
    with pytest.raises(ledger.OfflineRecoveryLedgerError):
        _run()
    assert calls == ["source", "sqlite", "chroma"]


def test_no_optional_chroma_does_not_false_claim_vector_recovery(monkeypatch):
    archive = _restored(
        ["backend_data", "mongo_config", "mongo_data", "skeleton_data"]
    )
    calls = _mock(monkeypatch, archive=archive)
    report = _run()
    assert calls == ["source", "sqlite", "source"]
    assert report["chroma_role_present"] is False
    assert report["chroma_hnsw_file_custody_verified"] is False
    assert report["chroma_persistent_segment_files_hashed"] == 0
    assert report["database_application_restore_qualified"] is False


def test_no_sqlite_is_explicitly_not_integrity_qualified(monkeypatch):
    empty = {**_sqlite_success(),
             "status": "no_restored_sqlite_candidates_not_database_qualified",
             "sqlite_databases_detected": 0,
             "sqlite_databases_integrity_checked": 0,
             "sqlite_total_bytes": 0,
             "all_detected_sqlite_integrity_ok": False}
    empty.pop("aggregate_content_fingerprint_sha256")
    _mock(monkeypatch, sqlite_receipt=empty)
    report = _run()
    assert report["sqlite_structural_integrity_verified"] is False
    assert report["sqlite_databases_checked"] == 0
    assert report["database_application_restore_qualified"] is False


def test_empty_chroma_segment_catalog_not_qualified(monkeypatch):
    empty = {**_chroma_success(),
             "status": "chroma_metadata_present_no_persistent_hnsw_segments",
             "persistent_vector_segments": 0,
             "all_index_files_present_and_hashed": False}
    empty.pop("aggregate_fingerprint_sha256")
    _mock(monkeypatch, chroma_receipt=empty)
    report = _run()
    assert report["chroma_hnsw_file_custody_verified"] is False
    assert report["chroma_role_present"] is True
    assert report["release_authorized"] is False


def test_subgate_exception_is_redacted_not_exposed(monkeypatch):
    calls = _mock(monkeypatch)
    def fail(*args, **kwargs):
        raise RuntimeError("MONGO_URL=mongodb://private:SECRET@server")
    monkeypatch.setattr(ledger.chroma, "inspect_restored_chroma", fail)
    with pytest.raises(ledger.OfflineRecoveryLedgerError) as err:
        _run()
    assert "SECRET" not in str(err.value)
    assert calls == ["source", "sqlite"]


def test_invalid_digest_denied_before_any_archive_call(monkeypatch):
    monkeypatch.setattr(ledger.restored, "verify_rehydration",
                        lambda *a, **kw: pytest.fail("untrusted SHA reached archive"))
    with pytest.raises(ledger.OfflineRecoveryLedgerError):
        ledger.audit_offline_recovery_evidence(
            SOURCE, Path("/fresh"), expected_receipt_sha256="nope",
        )


def test_end_to_end_real_synthetic_sqlite_and_chroma_index_fixture(
        tmp_path, monkeypatch):
    """Real integrity checks and file SHA on a fully synthetic in-memory role proof."""
    target, root, chroma_db, _ = chroma_fixture(tmp_path, monkeypatch)
    for role in ("backend_data", "skeleton_data"):
        (target / role).mkdir(mode=0o700)
    _database(target, "backend_data", "chat.sqlite3")
    _database(target, "skeleton_data", "memory.db")
    # The full archived-byte verifier is independently exercised in its
    # own suite. Here only it is mocked; SQLite/Chroma readers are real.
    archive = _restored()
    observed = []
    def verified(source, destination, *, expected_receipt_sha256):
        observed.append(destination)
        assert destination == target
        assert expected_receipt_sha256 == SHA
        return copy.deepcopy(archive)
    monkeypatch.setattr(ledger.restored, "verify_rehydration", verified)
    result = ledger.audit_offline_recovery_evidence(
        SOURCE, target, expected_receipt_sha256=SHA,
    )
    assert result["sqlite_databases_checked"] == 3
    assert result["chroma_hnsw_file_custody_verified"] is True
    assert result["chroma_persistent_segment_files_hashed"] == 5
    assert result["cross_store_transaction_coherence_qualified"] is False
    assert result["database_application_restore_qualified"] is False
    assert len(observed) >= 4


def test_ledger_does_not_use_docker_or_mongo_network(monkeypatch):
    _mock(monkeypatch)
    monkeypatch.setattr(ledger.host, "_run", lambda *a, **kw:
                        pytest.fail("offline ledger accessed Docker daemon"))
    assert _run()["release_authorized"] is False
