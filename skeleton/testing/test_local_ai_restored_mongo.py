"""Real disposable WiredTiger *file-byte* tests; never start mongod.

Only dummy marker files in a private pytest directory are created.
Their names and content are not a Mongo database; successful inventory
means source-file custody only, never Mongo logical replay or recovery.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import local_ai_restored_mongo as mongo

ARCHIVE_SHA = "a" * 64
SOURCE = Path("/no-live-backup")
_REQUIRED = (
    "WiredTiger", "WiredTiger.turtle", "WiredTiger.wt",
    "storage.bson", "_mdb_catalog.wt",
)
_DENIED = (
    "wiredtiger_page_parser_executed", "mongod_process_started",
    "mongo_journal_replayed", "mongo_logical_consistency_verified",
    "external_writer_quiescence_verified",
    "mongo_application_transactions_recovered",
    "sqlite_chroma_alignment_verified", "cross_store_snapshot_atomic",
    "application_restore_qualified", "protected_jeeves_chat_qualified",
    "release_authorized",
)


def _fixture(tmp_path, monkeypatch, *, journal=True, collection=True):
    tmp_path.chmod(0o700)
    destination = tmp_path / "fresh-private-restore"
    destination.mkdir(mode=0o700)
    data = destination / "mongo_data"
    data.mkdir(mode=0o700)
    for member in _REQUIRED:
        file = data / member
        file.write_bytes(b"SYNTHETIC MONGO WT FILE: " + member.encode("ascii"))
        file.chmod(0o600)
    if collection:
        for name in (
            "collection-00001-12345.wt", "index-00001-12345.wt",
        ):
            file = data / name
            file.write_bytes(b"SYNTHETIC WT PAGE BYTES:" + name.encode("ascii"))
            file.chmod(0o600)
    empty = data / "mongod.lock"
    empty.touch(mode=0o600)
    empty.chmod(0o600)
    if journal:
        folder = data / "journal"
        folder.mkdir(mode=0o700)
        log = folder / "WiredTigerLog.0000000001"
        log.write_bytes(b"SYNTHETIC UNREPLAYED LOG BYTES")
        log.chmod(0o600)
    volumes = ["backend_data", "chroma_data", "mongo_config",
               "mongo_data", "skeleton_data"]
    receipt = {
        "schema": mongo.restored.SCHEMA,
        "status": "all_cold_archive_files_rehydrated_not_database_restored",
        "source_receipt_file_sha256": ARCHIVE_SHA,
        "roles": volumes,
        "database_process_started": False,
        "docker_daemon_used": False,
        "mongo_consistency_verified": False,
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
        "receipt_sha256": "b" * 64,
    }
    calls = []
    def verified(source, target, *, expected_receipt_sha256):
        calls.append((source, target, expected_receipt_sha256))
        assert source == SOURCE
        assert target == destination
        assert expected_receipt_sha256 == ARCHIVE_SHA
        return copy.deepcopy(receipt)
    monkeypatch.setattr(mongo.restored, "verify_rehydration", verified)
    return destination, data, calls, receipt


def _audit(destination):
    return mongo.inspect_restored_mongo(
        SOURCE, destination, expected_receipt_sha256=ARCHIVE_SHA,
    )


def test_real_private_descriptor_hashes_classify_wiredtiger_without_mongod(
        tmp_path, monkeypatch, capsys):
    target, data, calls, receipt = _fixture(tmp_path, monkeypatch)
    before = {
        path.relative_to(data).as_posix(): path.read_bytes()
        for path in data.rglob("*") if path.is_file()
    }
    audit = _audit(target)
    assert audit["schema"] == mongo.SCHEMA
    assert audit["required_catalog_files_verified"] == 5
    assert audit["collection_files_observed"] == 1
    assert audit["index_files_observed"] == 1
    assert audit["journal_files_observed"] == 1
    assert audit["journal_file_bytes_present"] is True
    assert audit["hashed_wiredtiger_files"] == len(before)
    assert audit["hashed_wiredtiger_bytes"] == sum(map(len, before.values()))
    assert len(audit["aggregate_file_fingerprint_sha256"]) == 64
    assert audit["independent_cold_archive_verified_twice"] is True
    assert all(audit[name] is False for name in _DENIED)
    assert len(calls) == 2
    assert all(c[2] == ARCHIVE_SHA for c in calls)
    assert {
        path.relative_to(data).as_posix(): path.read_bytes()
        for path in data.rglob("*") if path.is_file()
    } == before
    output = str(audit) + str(capsys.readouterr())
    assert "SYNTHETIC MONGO" not in output
    assert str(data) not in output


def test_same_offline_copy_rehash_is_deterministic(tmp_path, monkeypatch):
    target, data, calls, _ = _fixture(tmp_path, monkeypatch)
    assert _audit(target) == _audit(target)
    assert len(calls) == 4


def test_no_journal_does_not_claim_transaction_replay(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch, journal=False)
    audit = _audit(target)
    assert audit["journal_files_observed"] == 0
    assert audit["journal_file_bytes_present"] is False
    assert audit["mongo_journal_replayed"] is False
    assert audit["mongo_logical_consistency_verified"] is False


def test_no_collections_does_not_claim_app_recovery(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch, collection=False)
    audit = _audit(target)
    assert audit["collection_files_observed"] == 0
    assert audit["application_restore_qualified"] is False


@pytest.mark.parametrize("required", _REQUIRED)
def test_missing_mongo_wiredtiger_catalog_marker_denied(
        tmp_path, monkeypatch, required):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    (data / required).unlink()
    with pytest.raises(mongo.MongoWiredTigerCustodyError, match="mandatory"):
        _audit(target)


@pytest.mark.parametrize("wrong", [
    "engine.secret", "WiredTiger.backup", "WiredTiger.turtle.bak",
    "admin-secrets.json", ".unknown", "collection-../../outside.wt",
])
def test_unknown_mongo_file_layout_fails_closed(
        tmp_path, monkeypatch, wrong):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    # A slash is itself an unsafe path and deliberately placed as a nested
    # directory to establish that unexpected directory layouts fail first.
    path = data / wrong
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(b"unsupported")
    path.chmod(0o600)
    with pytest.raises(mongo.MongoWiredTigerCustodyError):
        _audit(target)


def test_mongo_special_file_symlink_is_denied_not_followed(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    real = data / "WiredTiger.turtle"
    real.unlink()
    real.symlink_to(data / "WiredTiger.wt")
    with pytest.raises(mongo.MongoWiredTigerCustodyError):
        _audit(target)


def test_mongo_hardlinked_catalog_is_not_single_owner(tmp_path, monkeypatch):
    import os
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    os.link(data / "WiredTiger.turtle", data / "copied-turtle")
    with pytest.raises(mongo.MongoWiredTigerCustodyError):
        _audit(target)


def test_externally_readable_wt_bytes_denied(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    (data / "WiredTiger.wt").chmod(0o644)
    with pytest.raises(mongo.MongoWiredTigerCustodyError, match="private"):
        _audit(target)


def test_disallowed_journal_filename_cannot_be_claimed_replayed(
        tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    file = data / "journal" / "UnrecognizedLog.0000000001"
    file.write_bytes(b"UNREPLAYED DATA")
    file.chmod(0o600)
    with pytest.raises(mongo.MongoWiredTigerCustodyError, match="journal"):
        _audit(target)


def test_symlinked_journal_directory_denied(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    journal = data / "journal"
    journal.rename(data / "journal-old")
    journal.symlink_to(data / "journal-old", target_is_directory=True)
    with pytest.raises(mongo.MongoWiredTigerCustodyError):
        _audit(target)


def test_unexpected_nested_data_directory_denied(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    unexpected = data / "another-store"
    unexpected.mkdir(mode=0o700)
    with pytest.raises(mongo.MongoWiredTigerCustodyError, match="directory"):
        _audit(target)


def test_diagnostic_directory_allowed_but_not_called_mongo_recovery(
        tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    folder = data / "diagnostic.data"
    folder.mkdir(mode=0o700)
    proof = _audit(target)
    assert proof["diagnostic_directory_present"] is True
    assert proof["mongo_logical_consistency_verified"] is False


def test_private_file_open_is_pinned_by_dirfd_and_nofollow(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    original = mongo.os.open
    recorded = []
    def enforce(path, flags, *args, **kwargs):
        if isinstance(path, str) and path in _REQUIRED:
            assert kwargs.get("dir_fd") is not None
            assert flags & mongo.os.O_NOFOLLOW
            recorded.append(path)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(mongo.os, "open", enforce)
    assert _audit(target)["required_catalog_files_verified"] == 5
    assert set(recorded) == set(_REQUIRED)


def test_catalog_byte_change_during_hash_denied(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    original = mongo._hash_file
    mutate = []
    def malicious(fd, name, **kwargs):
        evidence = original(fd, name, **kwargs)
        if name == "WiredTiger.turtle" and not mutate:
            mutate.append(name)
            (data / name).write_bytes(b"maliciously modified after hash")
        return evidence
    monkeypatch.setattr(mongo, "_hash_file", malicious)
    with pytest.raises(mongo.MongoWiredTigerCustodyError):
        _audit(target)
    assert mutate == ["WiredTiger.turtle"]


def test_original_cold_receipt_drift_after_file_scan_denied(
        tmp_path, monkeypatch):
    target, data, calls, report = _fixture(tmp_path, monkeypatch)
    original = mongo.restored.verify_rehydration
    def drift(*a, **kw):
        value = original(*a, **kw)
        if len(calls) == 2:
            value["receipt_sha256"] = "d" * 64
        return value
    monkeypatch.setattr(mongo.restored, "verify_rehydration", drift)
    with pytest.raises(mongo.MongoWiredTigerCustodyError, match="changed"):
        _audit(target)


@pytest.mark.parametrize("change", [
    {"database_process_started": True},
    {"docker_daemon_used": True},
    {"mongo_consistency_verified": True},
    {"cross_store_snapshot_atomic": True},
    {"application_restore_qualified": True},
    {"roles": ["backend_data", "skeleton_data"]},
    {"receipt_sha256": "MALFORMED"},
])
def test_source_archive_cannot_elevate_mongo_authority(
        tmp_path, monkeypatch, change):
    target, data, calls, original = _fixture(tmp_path, monkeypatch)
    original.update(change)
    with pytest.raises(mongo.MongoWiredTigerCustodyError):
        _audit(target)
    assert len(calls) == 1


def test_bad_source_digest_refused_before_any_restore_check(
        tmp_path, monkeypatch):
    monkeypatch.setattr(mongo.restored, "verify_rehydration", lambda *a, **kw:
                        pytest.fail("malformed digest reached archive"))
    with pytest.raises(mongo.MongoWiredTigerCustodyError):
        mongo.inspect_restored_mongo(
            SOURCE, tmp_path, expected_receipt_sha256="MALFORMED"
        )


def test_archive_exception_is_redacted_without_database_password(
        tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    def fail(*args, **kwargs):
        raise RuntimeError("mongodb://user:PRIVATE_PASSWORD@mongo:27017")
    monkeypatch.setattr(mongo.restored, "verify_rehydration", fail)
    with pytest.raises(mongo.MongoWiredTigerCustodyError) as error:
        _audit(target)
    assert "PRIVATE_PASSWORD" not in str(error.value)


def test_no_docker_mongod_or_mongo_client_entered(tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(mongo.host, "_run", lambda *args, **kwargs:
                        pytest.fail("offline Mongo file scan used Docker"))
    assert _audit(target)["mongod_process_started"] is False


def test_unbounded_directory_entry_count_denied_before_file_read(
        tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    original = mongo._MAX_ROOT
    monkeypatch.setattr(mongo, "_MAX_ROOT", 5)
    monkeypatch.setattr(mongo, "_hash_file", lambda *a, **kw:
                        pytest.fail("excess directory files were already hashed"))
    with pytest.raises(mongo.MongoWiredTigerCustodyError, match="budget"):
        _audit(target)
    assert original > 5


def test_deadline_denied_during_hash_not_promoted_to_recovery(
        tmp_path, monkeypatch):
    target, data, _, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(mongo, "_hash_file", lambda *a, **kw:
                        (_ for _ in ()).throw(
                            mongo.MongoWiredTigerCustodyError(
                                "Mongo offline byte inventory exceeded deadline"
                            )
                        ))
    with pytest.raises(mongo.MongoWiredTigerCustodyError, match="deadline"):
        _audit(target)
