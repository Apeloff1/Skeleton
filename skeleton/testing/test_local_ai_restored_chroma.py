"""Physical private Chroma SQLite + HNSW file-envelope tests, no Chroma load.

Creates disposable SQLite segment catalogs and exact HNSW binary fixture files.
Never unpickles metadata, loads HNSW native index, connects Docker, reads real
tenants or implies that graph consistency/cross-store recovery was verified.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from uuid import UUID

import pytest

from scripts import local_ai_restored_chroma as chroma


SEGMENT = "6eaf4ac7-9e08-4bc8-924f-ef51b130856a"
METADATA_SEGMENT = "369958b0-75fa-4b6a-a59b-d2a4e211f7c6"
SECOND_SEGMENT = "82d43c0b-22cd-4e39-8c7e-21fe4d52ff33"
SOURCE = Path("/no-real-app-data")
EXPECTED_SHA = "a" * 64


def _fixture(tmp_path: Path, monkeypatch, *, indexed=True,
             vector_type=chroma._VECTOR_TYPE, extra_segments=()):
    target = tmp_path / "fresh-rehydrate"
    target.mkdir(mode=0o700)
    (target / "chroma_data").mkdir(mode=0o700)
    root = target / "chroma_data"
    dbpath = root / "chroma.sqlite3"
    with sqlite3.connect(dbpath) as conn:
        conn.execute(
            "CREATE TABLE segments "
            "(id TEXT PRIMARY KEY, type TEXT NOT NULL, scope TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO segments VALUES (?, ?, ?)",
            (METADATA_SEGMENT, "urn:chroma:segment/metadata/sqlite", "METADATA"),
        )
        conn.execute(
            "INSERT INTO segments VALUES (?, ?, ?)",
            (SEGMENT, vector_type, "VECTOR"),
        )
        for segment in extra_segments:
            conn.execute(
                "INSERT INTO segments VALUES (?, ?, ?)",
                (segment, vector_type, "VECTOR"),
            )
    dbpath.chmod(0o600)
    if indexed:
        for uuid in (SEGMENT, *extra_segments):
            _index(root, uuid)
    verified = {
        "roles": [
            "backend_data", "chroma_data", "mongo_config", "mongo_data",
            "skeleton_data",
        ],
        "database_process_started": False,
        "docker_daemon_used": False,
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
    }
    inspections = []
    def confirm(source, dest, *, expected_receipt_sha256):
        inspections.append((source, dest, expected_receipt_sha256))
        assert source == SOURCE
        assert dest == target
        assert expected_receipt_sha256 == EXPECTED_SHA
        return dict(verified)
    monkeypatch.setattr(chroma.rehydrate, "verify_rehydration", confirm)
    return target, root, dbpath, inspections


def _index(root: Path, uuid: str) -> Path:
    directory = root / uuid
    directory.mkdir(mode=0o700)
    for filename in sorted(chroma._INDEX):
        payload = (b"HEADER" * 17 if filename == "header.bin"
                   else (b"\x80\x04malicious-pickle-never-load" if filename ==
                         "index_metadata.pickle" else b"BINARY" * 15))
        file = directory / filename
        file.write_bytes(payload)
        file.chmod(0o600)
    return directory


def _inspect(destination):
    return chroma.inspect_restored_chroma(
        SOURCE, destination, expected_receipt_sha256=EXPECTED_SHA,
    )


def test_real_sqlite_segment_rows_and_index_file_hashes_are_attested(
        tmp_path, monkeypatch):
    destination, root, dbpath, calls = _fixture(tmp_path, monkeypatch)
    before = {
        f.relative_to(root).as_posix(): f.read_bytes()
        for f in root.rglob("*") if f.is_file()
    }
    proof = _inspect(destination)
    assert len(calls) == 1
    assert proof["schema"] == chroma.SCHEMA
    assert proof["persistent_vector_segments"] == 1
    assert proof["hashed_index_files"] == 5
    assert proof["all_index_files_present_and_hashed"] is True
    assert proof["catalog_and_segment_file_identity_verified"] is True
    assert len(proof["aggregate_fingerprint_sha256"]) == 64
    assert proof["pickle_deserialized"] is False
    for denied in (
        "hnsw_graph_load_qualified", "chroma_logical_replay_qualified",
        "mongo_consistency_verified", "cross_store_snapshot_atomic",
        "application_restore_qualified", "release_authorized",
        "protected_jeeves_chat_qualified", "source_archive_modified",
        "restored_bytes_modified",
    ):
        assert proof[denied] is False
    assert {
        f.relative_to(root).as_posix(): f.read_bytes()
        for f in root.rglob("*") if f.is_file()
    } == before
    assert SEGMENT not in str(proof)
    assert "malicious-pickle" not in str(proof)
    assert str(root) not in str(proof)


def test_two_vector_segments_are_sorted_and_fingerprinted_stably(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(
        tmp_path, monkeypatch, extra_segments=(SECOND_SEGMENT,),
    )
    a = _inspect(target)
    b = _inspect(target)
    assert a == b
    assert a["persistent_vector_segments"] == 2
    assert a["hashed_index_files"] == 10
    assert a["all_index_files_present_and_hashed"] is True


@pytest.mark.parametrize("role", [
    "chroma_data", "backend_data",
])
def test_unverified_or_wrong_source_prerequisites_never_scan_database(
        tmp_path, monkeypatch, role):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(chroma.rehydrate, "verify_rehydration", lambda *a, **kw:
                        (_ for _ in ()).throw(
                            RuntimeError("PRIVATE ARCHIVE TOKEN")
                        ))
    with pytest.raises(chroma.ChromaCustodyError) as error:
        _inspect(target)
    assert "PRIVATE" not in str(error.value)


def test_malformed_cold_role_inventory_denies_chroma_claim(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(chroma.rehydrate, "verify_rehydration",
                        lambda *a, **kw: {
                            "roles": ["backend_data", "skeleton_data"],
                            "database_process_started": False,
                            "docker_daemon_used": False,
                            "cross_store_snapshot_atomic": False,
                            "application_restore_qualified": False,
                        })
    with pytest.raises(chroma.ChromaCustodyError, match="prerequisite"):
        _inspect(target)


@pytest.mark.parametrize("remove", tuple(chroma._INDEX))
def test_missing_hnsw_member_never_qualifies_segment(
        tmp_path, monkeypatch, remove):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    (root / SEGMENT / remove).unlink()
    with pytest.raises(chroma.ChromaCustodyError, match="incomplete"):
        _inspect(target)


def test_extra_segment_binary_fails_unknown_file_contract(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    extra = root / SEGMENT / "untrusted.bin"
    extra.write_bytes(b"PRIVATE PAYLOAD")
    extra.chmod(0o600)
    with pytest.raises(chroma.ChromaCustodyError, match="unrecognized"):
        _inspect(target)


def test_malicious_pickle_payload_is_never_executed_or_deserialized(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    import pickle
    monkeypatch.setattr(pickle, "load", lambda *a, **kw:
                        pytest.fail("pickle deserialized during Chroma custody"))
    monkeypatch.setattr(pickle, "loads", lambda *a, **kw:
                        pytest.fail("pickle deserialized during Chroma custody"))
    assert _inspect(target)["pickle_deserialized"] is False


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sqlite_journal_sidecars_are_denied_before_index_catalog_use(
        tmp_path, monkeypatch, suffix):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    sidecar = Path(str(db) + suffix)
    sidecar.write_bytes(b"UNACKNOWLEDGED SQLITE STATE")
    sidecar.chmod(0o600)
    with pytest.raises(chroma.ChromaCustodyError):
        _inspect(target)


def test_vector_segment_without_persisted_directory_fails_closed(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch, indexed=False)
    with pytest.raises(chroma.ChromaCustodyError, match="inventory differ"):
        _inspect(target)


def test_stale_unreferenced_segment_directory_denied(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    _index(root, SECOND_SEGMENT)
    with pytest.raises(chroma.ChromaCustodyError, match="inventory differ"):
        _inspect(target)


def test_empty_catalog_is_not_false_chroma_recovery_proof(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    (root / SEGMENT).rename(root / "to-delete")
    for member in (root / "to-delete").iterdir():
        member.unlink()
    (root / "to-delete").rmdir()
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM segments WHERE scope='VECTOR'")
    proof = _inspect(target)
    assert proof["persistent_vector_segments"] == 0
    assert proof["all_index_files_present_and_hashed"] is False
    assert proof["hnsw_graph_load_qualified"] is False
    assert proof["application_restore_qualified"] is False


def test_unsupported_vector_index_type_requires_separate_qualification(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(
        tmp_path, monkeypatch, vector_type="urn:chroma:segment/vector/unknown",
    )
    with pytest.raises(chroma.ChromaCustodyError, match="unrecognized"):
        _inspect(target)


def test_chroma_catalog_missing_segments_table_denied(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE segments")
    with pytest.raises(chroma.ChromaCustodyError, match="schema"):
        _inspect(target)


def test_invalid_segment_uuid_never_becomes_a_filesystem_path(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE segments SET id = ? WHERE scope='VECTOR'",
            ("../../persistence",),
        )
    with pytest.raises(chroma.ChromaCustodyError, match="identity"):
        _inspect(target)


def test_duplicate_vector_id_is_rejected_when_database_lacks_primary_key(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE segments RENAME TO old_segments")
        conn.execute("CREATE TABLE segments (id TEXT, type TEXT, scope TEXT)")
        conn.execute("INSERT INTO segments SELECT * FROM old_segments")
        conn.execute(
            "INSERT INTO segments VALUES (?, ?, ?)",
            (SEGMENT, chroma._VECTOR_TYPE, "VECTOR"),
        )
        conn.execute("DROP TABLE old_segments")
    with pytest.raises(chroma.ChromaCustodyError, match="duplicate"):
        _inspect(target)


def test_index_symlink_never_trusted_as_real_binary(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    member = root / SEGMENT / "data_level0.bin"
    member.unlink()
    member.symlink_to(root / SEGMENT / "header.bin")
    with pytest.raises(chroma.ChromaCustodyError, match="private"):
        _inspect(target)


def test_world_readable_index_binary_denied(tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    (root / SEGMENT / "header.bin").chmod(0o644)
    with pytest.raises(chroma.ChromaCustodyError, match="private"):
        _inspect(target)


def test_truncated_index_header_denied(tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    (root / SEGMENT / "header.bin").write_bytes(b"bad")
    with pytest.raises(chroma.ChromaCustodyError, match="header"):
        _inspect(target)


def test_unrecognized_directory_inside_chroma_root_denied(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    folder = root / "untrusted-cache"
    folder.mkdir(mode=0o700)
    with pytest.raises(chroma.ChromaCustodyError, match="inventory differ"):
        _inspect(target)


def test_deadline_denies_index_hash_instead_of_unbounded_read(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    original = chroma._hash_index
    called = 0
    def stopped(path, *, deadline):
        nonlocal called
        called += 1
        raise chroma.ChromaCustodyError("Chroma HNSW hash deadline exceeded")
    monkeypatch.setattr(chroma, "_hash_index", stopped)
    with pytest.raises(chroma.ChromaCustodyError, match="deadline"):
        _inspect(target)
    assert called == 1


def test_binary_mutation_during_hash_does_not_pass(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    original = chroma._hash_index
    called = 0
    def mutate(path, *, deadline):
        nonlocal called
        called += 1
        result = original(path, deadline=deadline)
        if called == 1:
            path.write_bytes(path.read_bytes() + b"tamper")
        return result
    monkeypatch.setattr(chroma, "_hash_index", mutate)
    with pytest.raises(chroma.ChromaCustodyError, match="changed"):
        _inspect(target)


def test_no_live_chroma_client_is_imported_or_docker_called(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(chroma.host, "_run", lambda *a, **kw:
                        pytest.fail("offline Chroma audit reached Docker"))
    assert _inspect(target)["all_index_files_present_and_hashed"] is True
    import inspect
    code = inspect.getsource(chroma)
    assert "pickle.loads(" not in code
    assert "chromadb.PersistentClient(" not in code
    assert "docker compose" not in code


def test_operator_chroma_audit_passes_independent_receipt_without_docker(
        monkeypatch, tmp_path, capsys):
    from scripts import local_ai_docker as operator
    expected = {
        "schema": chroma.SCHEMA,
        "status": "read_only_legacy_hnsw_file_custody_not_chroma_recovery",
        "release_authorized": False,
    }
    history = []
    def qualified(source, destination, *, expected_receipt_sha256):
        history.append((source, destination, expected_receipt_sha256))
        return dict(expected)
    monkeypatch.setattr(chroma, "inspect_restored_chroma", qualified)
    monkeypatch.setattr(operator, "_run", lambda *a, **kw:
                        pytest.fail("read-only Chroma operator called Docker"))
    assert operator.main([
        "--mode", "cpu", "audit-restored-chroma",
        "--source", str(tmp_path / "archive"),
        "--destination", str(tmp_path / "restored"),
        "--expected-receipt-sha256", EXPECTED_SHA,
    ]) == 0
    stdout, stderr = capsys.readouterr()
    assert stderr == ""
    import json
    assert json.loads(stdout) == expected
    assert history == [
        (tmp_path / "archive", tmp_path / "restored", EXPECTED_SHA),
    ]


def test_binary_digest_deadline_is_enforced_during_stream(
        tmp_path, monkeypatch):
    target, root, db, _ = _fixture(tmp_path, monkeypatch)
    real_monotonic = chroma.time.monotonic
    fake_calls = 0
    def expired():
        nonlocal fake_calls
        fake_calls += 1
        if fake_calls > 13:
            return real_monotonic() + 1000
        return real_monotonic()
    monkeypatch.setattr(chroma.time, "monotonic", expired)
    with pytest.raises(chroma.ChromaCustodyError, match="deadline"):
        _inspect(target)


def test_invalid_uuid_case_or_version_is_denied():
    with pytest.raises(chroma.ChromaCustodyError):
        chroma._uuid(SEGMENT.upper())
    with pytest.raises(chroma.ChromaCustodyError):
        chroma._uuid("00000000-0000-0000-0000-000000000000")
    with pytest.raises(chroma.ChromaCustodyError):
        chroma._uuid(True)
