"""P0 data-lifecycle erasure regressions."""

from __future__ import annotations

import json

import pytest

from skeleton.memory.core import Chunk
from skeleton.memory.vector import VectorStore
from skeleton.reliability.backup_restore import BackupManager


def test_vector_source_purge_removes_all_derived_embeddings() -> None:
    store = VectorStore(dims=16)
    store.add(
        Chunk("alpha source fragment one", chunk_id="a-1"),
        source_id="source-a",
    )
    store.add(
        Chunk("alpha source fragment two", chunk_id="a-2"),
        source_id="source-a",
    )
    store.add(
        Chunk("beta retained fragment", chunk_id="b-1"),
        source_id="source-b",
    )

    assert store.purge_source("source-a") == 2
    assert store.purge_source("source-a") == 0
    assert store.stats()["documents"] == 1
    assert set(store._entries) == {"b-1"}
    assert store._entries["b-1"].source_id == "source-b"


def test_vector_source_identity_can_follow_source_metadata() -> None:
    store = VectorStore(dims=16)
    store.add(
        Chunk(
            "derived searchable content",
            chunk_id="derived-1",
            metadata={"source_id": "document-42"},
        )
    )

    assert store._entries["derived-1"].source_id == "document-42"
    assert store.purge_source("document-42") == 1
    assert store.stats()["documents"] == 0


def test_backup_history_purge_removes_deleted_sensitive_state(tmp_path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    (root / "events.jsonl").write_text('{"event":"keep"}\n', encoding="utf-8")
    (root / "secrets.json").write_text('{"token":"first-secret"}', encoding="utf-8")

    manager = BackupManager(root)
    first = manager.backup("first")

    (root / "secrets.json").write_text(
        '{"token":"second-secret"}',
        encoding="utf-8",
    )
    second = manager.backup("second", incremental=True)
    (root / "secrets.json").unlink()

    assert manager.purge_file_history("secrets.json") == 2

    for entry in manager.list_backups():
        blob = json.loads(
            (manager.backup_dir / f"{entry['backup_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        assert "secrets.json" not in blob["files"]
        assert "secrets.json" not in blob["checksums"]
        assert "secrets.json" not in entry["files"]
        assert "secrets.json" not in entry["checksums"]
        assert manager.verify(entry["backup_id"])["valid"] is True

    assert "events.jsonl" in manager.list_backups()[0]["files"]

    (root / "events.jsonl").unlink()
    manager.restore(first["backup_id"], dry_run=False)
    assert (root / "events.jsonl").exists()
    assert not (root / "secrets.json").exists()
    assert second["backup_id"] in {
        item["backup_id"] for item in manager.list_backups()
    }


def test_backup_deletion_is_physical_and_ids_are_not_reused(tmp_path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    (root / "events.jsonl").write_text("one\n", encoding="utf-8")

    manager = BackupManager(root)
    first = manager.backup("first")
    (root / "events.jsonl").write_text("two\n", encoding="utf-8")
    second = manager.backup("second")
    (root / "events.jsonl").write_text("three\n", encoding="utf-8")
    third = manager.backup("third")

    second_path = manager.backup_dir / f"{second['backup_id']}.json"
    assert second_path.exists()
    assert manager.delete_backup(second["backup_id"]) is True
    assert not second_path.exists()
    assert manager.delete_backup(second["backup_id"]) is False

    (root / "events.jsonl").write_text("four\n", encoding="utf-8")
    fourth = manager.backup("fourth")
    assert first["backup_id"] == "b0001"
    assert third["backup_id"] == "b0003"
    assert fourth["backup_id"] == "b0004"


@pytest.mark.parametrize("backup_id", ("../escape", "backup-1", "b", ""))
def test_backup_identity_rejects_noncanonical_paths(tmp_path, backup_id: str) -> None:
    manager = BackupManager(tmp_path / "state")
    with pytest.raises(ValueError, match="invalid backup_id"):
        manager.verify(backup_id)
