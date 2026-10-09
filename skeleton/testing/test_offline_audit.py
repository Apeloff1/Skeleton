"""Semantic corruption detection beyond raw SQLite integrity and file hashes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from skeleton.app.offline_audit import AUDIT_SCHEMA, OfflineAuditError, audit_database
from skeleton.app.offline_cli import main as offline_cli
from skeleton.app.offline_snapshot import (
    OfflineSnapshotError, create_snapshot, verify_snapshot,
)
from skeleton.app.offline_workspace import OfflineWorkspace
from skeleton.app.offline_library import OfflineDocumentLibrary
from skeleton.app.offline_index_queue import OfflineIndexQueue
from skeleton.app.cli import run_app_cli


MODEL = "a" * 64


def _fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "facts.md").write_text("Local deterministic physics knowledge.", encoding="utf-8")
    workspace = tmp_path / "conversation.db"
    library = tmp_path / "knowledge.db"
    queue = tmp_path / "jobs.db"
    with OfflineWorkspace(workspace) as store:
        store.open("chat", MODEL)
        store.save("chat", MODEL, 0, (("user", "Hello"), ("assistant", "Offline.")))
    with OfflineDocumentLibrary(library) as store:
        store.index_directory(docs)
    with OfflineIndexQueue(queue) as store:
        store.enqueue(docs, library)
        result = store.run_one()
        assert result is not None and result.state == "completed"
    return workspace, library, queue


def _change(path: Path, statement: str, params: tuple = ()) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(statement, params)


def test_deep_audit_checks_all_three_local_state_domains(tmp_path: Path) -> None:
    workspace, library, queue = _fixtures(tmp_path)
    a = audit_database(workspace, "workspace")
    b = audit_database(library, "library")
    c = audit_database(queue, "queue")
    assert a["schema_version"] == AUDIT_SCHEMA
    assert a["complete_turns"] == 1
    assert b["documents"] == 1
    assert b["indexed_bytes"] > 0
    assert c["jobs"] == 1
    assert c["pending_jobs"] == 0


def test_workspace_message_tampering_is_rejected_even_if_sqlite_is_valid(
    tmp_path: Path,
) -> None:
    workspace, _, _ = _fixtures(tmp_path)
    _change(workspace, "UPDATE offline_conversations SET history_json='[]'")
    with pytest.raises(OfflineAuditError, match="conversation"):
        audit_database(workspace, "workspace")


def test_fts_projection_mismatch_is_rejected_with_matching_document_hash(
    tmp_path: Path,
) -> None:
    _, library, _ = _fixtures(tmp_path)
    changed = "A different knowledge document"
    digest = hashlib.sha256(changed.encode("utf-8")).hexdigest()
    _change(library, "UPDATE offline_documents SET body=?, sha256=?, size_bytes=?",
            (changed, digest, len(changed.encode("utf-8"))))
    with pytest.raises(OfflineAuditError, match="FTS5|document"):
        audit_database(library, "library")


def test_orphaned_fts_row_is_detected(tmp_path: Path) -> None:
    _, library, _ = _fixtures(tmp_path)
    _change(library, "INSERT INTO offline_document_fts(rowid, body) VALUES (?,?)",
            (99999, "orphan knowledge"))
    with pytest.raises(OfflineAuditError, match="FTS5"):
        audit_database(library, "library")


def test_forged_successful_queue_job_requires_real_result(tmp_path: Path) -> None:
    _, _, queue = _fixtures(tmp_path)
    _change(queue, "UPDATE offline_index_jobs SET result_json=NULL WHERE state='completed'")
    with pytest.raises(OfflineAuditError, match="result"):
        audit_database(queue, "queue")


def test_snapshot_validation_requires_semantics_not_just_file_digest(
    tmp_path: Path,
) -> None:
    workspace, _, _ = _fixtures(tmp_path)
    snapshot = tmp_path / "backup"
    create_snapshot(snapshot, workspace=workspace)
    saved = snapshot / "workspace.sqlite"
    _change(saved, "UPDATE offline_conversations SET history_json='[]'")
    manifest = snapshot / "manifest.json"
    obj = json.loads(manifest.read_text("utf-8"))
    obj["databases"]["workspace"]["sha256"] = hashlib.sha256(saved.read_bytes()).hexdigest()
    obj["databases"]["workspace"]["size_bytes"] = saved.stat().st_size
    manifest.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(OfflineSnapshotError, match="semantic integrity"):
        verify_snapshot(snapshot)


def test_standalone_and_unified_cli_audit_without_mutation(
    tmp_path: Path, capsys,
) -> None:
    workspace, library, queue = _fixtures(tmp_path)
    args = [
        "--audit-workspace", str(workspace),
        "--audit-library", str(library),
        "--audit-queue", str(queue), "--json",
    ]
    assert offline_cli(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert set(output["reports"]) == {"workspace", "library", "queue"}
    assert run_app_cli(["local-ai", *args]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert offline_cli(["--audit-queue", str(queue), "--prompt", "never invoke"]) == 2

def test_doctor_cannot_silently_ignore_mutating_flags(
    tmp_path: Path, capsys,
) -> None:
    database = tmp_path / "local.db"
    assert offline_cli(["--queue-db", str(database), "--doctor", "--model", "missing"]) == 2
    assert offline_cli(["--snapshot-workspace", str(database), "--doctor", "--model", "missing"]) == 2
    assert offline_cli([
        "--audit-queue", str(database), "--snapshot-to", str(tmp_path / "backup"),
    ]) == 2
    assert offline_cli([
        "--audit-queue", str(database), "--queue-db", str(database), "--queue-status",
    ]) == 2
    assert capsys.readouterr().out == ""
