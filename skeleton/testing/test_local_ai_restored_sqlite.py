"""Real read-only SQLite structural audit over PRIVATE synthetic restored files.

Fixture databases are created only inside pytest private tmp dirs. No Docker
daemon, Mongo, mounted volume, app account or production data is accessed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from scripts import local_ai_restored_sqlite as audit


def _private_fixture(tmp_path: Path, monkeypatch, *, roles=None):
    target = tmp_path / "new-private-restore"
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    for role in ("mongo_data", "mongo_config", "backend_data", "skeleton_data"):
        (target / role).mkdir(mode=0o700)
    stated_roles = sorted(
        roles or ("mongo_data", "mongo_config", "backend_data", "skeleton_data")
    )
    if "chroma_data" in stated_roles:
        (target / "chroma_data").mkdir(mode=0o700)
    verified = {
        "schema": audit.rehydrate.SCHEMA,
        "roles": stated_roles,
        "database_process_started": False,
        "docker_daemon_used": False,
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
        "sqlite_consistency_verified": False,
    }
    observed = []
    def confirmed(source, destination, *, expected_receipt_sha256):
        observed.append((source, destination, expected_receipt_sha256))
        assert destination == target
        assert expected_receipt_sha256 == "a" * 64
        return verified
    monkeypatch.setattr(audit.rehydrate, "verify_rehydration", confirmed)
    return target, observed


def _database(root: Path, role="backend_data", name="chat.sqlite3",
              *, value="CONFIDENTIAL LOCAL AI MEMORY") -> Path:
    path = root / role / name
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE private_messages (id INTEGER PRIMARY KEY, content TEXT)")
        db.execute("INSERT INTO private_messages(content) VALUES (?)", (value,))
    path.chmod(0o600)
    return path


def _run(root, *, count=32):
    return audit.verify_restored_sqlite(
        Path("/non-production-archive"), root,
        expected_receipt_sha256="a" * 64, max_databases=count,
    )


def test_two_real_sqlite_databases_are_independently_integrity_checked(
        tmp_path, monkeypatch, capsys):
    restored, observed = _private_fixture(tmp_path, monkeypatch)
    first = _database(restored, "backend_data")
    second = _database(restored, "skeleton_data", "memory.db")
    bytes_before = [path.read_bytes() for path in (first, second)]
    report = _run(restored)
    assert report["schema"] == audit.SCHEMA
    assert report["sqlite_databases_detected"] == 2
    assert report["sqlite_databases_integrity_checked"] == 2
    assert report["all_detected_sqlite_integrity_ok"] is True
    assert report["sqlite_total_bytes"] == sum(map(len, bytes_before))
    assert len(report["aggregate_content_fingerprint_sha256"]) == 64
    assert all(report[key] is False for key in (
        "sqlite_wal_or_journal_accepted", "mongo_consistency_verified",
        "chroma_consistency_verified", "cross_store_snapshot_atomic",
        "application_restore_qualified", "protected_jeeves_chat_qualified",
        "release_authorized", "source_archive_modified",
        "restored_bytes_modified", "docker_daemon_used",
    ))
    assert len(observed) == 1
    assert [path.read_bytes() for path in (first, second)] == bytes_before
    printed = str(report) + str(capsys.readouterr())
    assert "CONFIDENTIAL" not in printed
    assert str(restored) not in printed


def test_sqlite_integrity_audit_does_not_require_docker_or_network(
        tmp_path, monkeypatch):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    _database(root)
    monkeypatch.setattr(audit.host, "_run", lambda *a, **kw:
                        pytest.fail("read-only SQLite audit used Docker"))
    assert _run(root)["all_detected_sqlite_integrity_ok"] is True


def test_no_sqlite_candidates_cannot_be_called_sqlite_integrity_proof(
        tmp_path, monkeypatch):
    restored, _ = _private_fixture(tmp_path, monkeypatch)
    report = _run(restored)
    assert report["sqlite_databases_detected"] == 0
    assert report["all_detected_sqlite_integrity_ok"] is False
    assert report["application_restore_qualified"] is False
    assert "aggregate_content_fingerprint_sha256" not in report


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_any_unresolved_sqlite_sidecar_denies_immutable_mode(
        tmp_path, monkeypatch, suffix):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    db = _database(root)
    tail = db.parent / (db.name + suffix)
    tail.write_bytes(b"synthetic-uncheckpointed-state")
    tail.chmod(0o600)
    monkeypatch.setattr(audit, "_integrity", lambda *a, **k:
                        pytest.fail("sidecar present: never open immutable SQLite"))
    with pytest.raises(audit.RestoredSQLiteError, match="sidecar"):
        _run(root)


def test_corrupt_sqlite_header_cannot_qualify_logical_integrity(
        tmp_path, monkeypatch):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    path = root / "backend_data" / "messages.sqlite"
    path.write_bytes(b"NOT SQLITE DATABASE")
    path.chmod(0o600)
    with pytest.raises(audit.RestoredSQLiteError, match="unavailable"):
        _run(root)


def test_foreign_key_integrity_violation_does_not_pass(
        tmp_path, monkeypatch):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    path = root / "backend_data" / "relationships.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE principals (id INTEGER PRIMARY KEY)")
        db.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY,"
            " principal_id INTEGER REFERENCES principals(id))"
        )
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("INSERT INTO messages(id, principal_id) VALUES (1, 700)")
    path.chmod(0o600)
    with pytest.raises(audit.RestoredSQLiteError, match="foreign keys"):
        _run(root)


@pytest.mark.parametrize("mode", [0o644, 0o666, 0o755])
def test_world_readable_private_database_is_denied(
        tmp_path, monkeypatch, mode):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    db = _database(root)
    db.chmod(mode)
    with pytest.raises(audit.RestoredSQLiteError, match="private"):
        _run(root)


def test_symlinked_sqlite_file_is_denied_by_walk_before_sqlite_connect(
        tmp_path, monkeypatch):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    outside = _database(root, "skeleton_data", "real.sqlite3")
    forged = root / "backend_data" / "fake.sqlite3"
    forged.symlink_to(outside)
    with pytest.raises(audit.RestoredSQLiteError, match="untrusted"):
        _run(root)


def test_database_count_budget_is_strictly_bounded_before_any_db_read(
        tmp_path, monkeypatch):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    for number in range(33):
        db = root / "backend_data" / f"test{number:02d}.db"
        db.write_bytes(b"unused-synthetic")
        db.chmod(0o600)
    monkeypatch.setattr(audit, "_integrity", lambda *a, **k:
                        pytest.fail("unbounded SQLite inventory launched DB reads"))
    with pytest.raises(audit.RestoredSQLiteError, match="count"):
        _run(root)


@pytest.mark.parametrize("limit", [0, -1, 33, True, False, None, "32"])
def test_invalid_limit_denied_before_any_source_access(
        tmp_path, monkeypatch, limit):
    monkeypatch.setattr(audit.rehydrate, "verify_rehydration",
                        lambda *args, **kwargs:
                        pytest.fail("invalid max_databases reached source"))
    with pytest.raises(audit.RestoredSQLiteError, match="limit"):
        audit.verify_restored_sqlite(
            tmp_path, tmp_path, expected_receipt_sha256="a"*64,
            max_databases=limit,
        )


def test_tampered_source_receipt_denied_before_local_sqlite_scan(
        tmp_path, monkeypatch):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(audit.rehydrate, "verify_rehydration",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            RuntimeError("secret Mongo credentials")
                        ))
    with pytest.raises(audit.RestoredSQLiteError) as error:
        _run(root)
    assert "secret Mongo" not in str(error.value)


def test_rehydrate_cannot_escalate_sqlite_custody_or_restore_claim(
        tmp_path, monkeypatch):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(audit.rehydrate, "verify_rehydration",
                        lambda *a, **kw: {
                            "roles": ["mongo_data", "mongo_config",
                                      "backend_data", "skeleton_data"],
                            "database_process_started": False,
                            "docker_daemon_used": False,
                            "cross_store_snapshot_atomic": True,
                            "application_restore_qualified": False,
                            "sqlite_consistency_verified": True,
                        })
    with pytest.raises(audit.RestoredSQLiteError, match="prerequisite"):
        _run(root)


def test_read_only_file_hash_drift_denies_integrity(
        tmp_path, monkeypatch):
    root, _ = _private_fixture(tmp_path, monkeypatch)
    _database(root)
    original = audit.worker._digest_file
    called = 0
    def corrupt_after(path, *, expected_size=None):
        nonlocal called
        called += 1
        digest, length = original(path, expected_size=expected_size)
        if called == 2:
            digest = "b" * 64
        return digest, length
    monkeypatch.setattr(audit.worker, "_digest_file", corrupt_after)
    with pytest.raises(audit.RestoredSQLiteError, match="changed"):
        _run(root)
    assert called == 2


def test_optional_chroma_sqlite_is_independently_checked_but_chroma_unqualified(
        tmp_path, monkeypatch):
    roles = ("mongo_data", "mongo_config", "backend_data",
             "skeleton_data", "chroma_data")
    root, _ = _private_fixture(tmp_path, monkeypatch, roles=roles)
    _database(root, "chroma_data", "chroma.sqlite3")
    receipt = _run(root)
    assert receipt["sqlite_databases_integrity_checked"] == 1
    assert receipt["chroma_consistency_verified"] is False
    assert receipt["application_restore_qualified"] is False
