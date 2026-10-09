"""Offline SQLite recovery contract and CLI acceptance tests."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from skeleton.app.offline_snapshot import (
    OfflineSnapshotError, create_snapshot, verify_snapshot, restore_snapshot,
)
from skeleton.app.offline_workspace import OfflineWorkspace
from skeleton.app.offline_library import OfflineDocumentLibrary
from skeleton.app.offline_index_queue import OfflineIndexQueue
from skeleton.app.offline_cli import main as offline_main
from skeleton.app.cli import run_app_cli

MODEL = "a" * 64


def _example(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "notes"
    source.mkdir()
    (source / "physics.md").write_text("Physics replay and deterministic frame state.")
    workspace = tmp_path / "chat.sqlite"
    library = tmp_path / "docs.sqlite"
    queue = tmp_path / "jobs.sqlite"
    with OfflineWorkspace(workspace) as store:
        store.open("local", MODEL)
        store.save("local", MODEL, 0, (
            ("user", "hello"), ("assistant", "offline answer"),
        ))
    with OfflineDocumentLibrary(library) as store:
        store.index_directory(source)
    with OfflineIndexQueue(queue) as store:
        store.enqueue(source, library)
    return workspace, library, queue


def test_full_local_state_backup_and_restore(tmp_path: Path) -> None:
    workspace, library, queue = _example(tmp_path)
    snapshot = tmp_path / "portable"
    manifest = create_snapshot(
        snapshot, workspace=workspace, library=library, queue=queue,
    )
    assert verify_snapshot(snapshot) == manifest
    assert set(manifest["databases"]) == {"workspace", "library", "queue"}
    assert manifest["consistent_across_databases"] is False
    assert manifest["signed"] is False
    chat2 = tmp_path / "restored-chat.sqlite"
    docs2 = tmp_path / "restored-docs.sqlite"
    queue2 = tmp_path / "restored-jobs.sqlite"
    restore_snapshot(snapshot, workspace=chat2, library=docs2, queue=queue2)
    with OfflineWorkspace(chat2) as store:
        revision, history = store.open("local", MODEL)
        assert revision == 1
        assert history[0] == ("user", "hello")
    with OfflineDocumentLibrary(docs2) as store:
        assert store.search("physics")[0].relative_path == "physics.md"
    with OfflineIndexQueue(queue2) as store:
        assert len(store.list_jobs()) == 1
        recovered_job = store.list_jobs()[0]
        assert recovered_job.state == "cancelled"
        assert "explicitly enqueue" in recovered_job.last_error
        assert store.run_one() is None
        with pytest.raises(Exception, match="terminal failed"):
            store.retry(recovered_job.job_id)


def test_live_sqlite_wal_is_saved_consistently(tmp_path: Path) -> None:
    workspace, _, _ = _example(tmp_path)
    with OfflineWorkspace(workspace) as store:
        store.open("second", MODEL)
        store.save("second", MODEL, 0, (
            ("user", "another"), ("assistant", "response"),
        ))
        create_snapshot(tmp_path / "portable", workspace=workspace)
    destination = tmp_path / "recovered.sqlite"
    restore_snapshot(tmp_path / "portable", workspace=destination)
    with OfflineWorkspace(destination) as recovered:
        assert recovered.open("second", MODEL)[1][1][1] == "response"


def test_checksum_rejects_corruption_and_unknown_files(tmp_path: Path) -> None:
    workspace, _, _ = _example(tmp_path)
    snapshot = tmp_path / "portable"
    create_snapshot(snapshot, workspace=workspace)
    database = snapshot / "workspace.sqlite"
    with database.open("ab") as writer:
        writer.write(b"changed")
    with pytest.raises(OfflineSnapshotError, match="checksum"):
        verify_snapshot(snapshot)
    with database.open("r+b") as writer:
        writer.seek(-7, 2)
        writer.truncate()
    assert verify_snapshot(snapshot)
    (snapshot / "unexpected.txt").write_text("unexpected")
    with pytest.raises(OfflineSnapshotError, match="unexpected"):
        verify_snapshot(snapshot)


def test_restore_requires_new_distinct_output_paths(tmp_path: Path) -> None:
    workspace, library, _ = _example(tmp_path)
    snapshot = tmp_path / "portable"
    create_snapshot(snapshot, workspace=workspace, library=library)
    existing = tmp_path / "existing.sqlite"
    existing.write_bytes(b"keep")
    fresh = tmp_path / "fresh.sqlite"
    with pytest.raises(OfflineSnapshotError, match="destination"):
        restore_snapshot(snapshot, workspace=fresh, library=existing)
    assert existing.read_bytes() == b"keep"
    assert not fresh.exists()
    with pytest.raises(OfflineSnapshotError, match="match"):
        restore_snapshot(snapshot, workspace=fresh)


def test_console_snapshot_and_app_verify_and_restore(tmp_path: Path, capsys) -> None:
    workspace, library, queue = _example(tmp_path)
    snapshot = tmp_path / "portable"
    assert offline_main([
        "--snapshot-to", str(snapshot),
        "--snapshot-workspace", str(workspace),
        "--snapshot-library", str(library),
        "--snapshot-queue", str(queue), "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["action"] == "created"
    assert run_app_cli([
        "local-ai", "--verify-snapshot", str(snapshot), "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["action"] == "verified"
    assert offline_main([
        "--restore-from", str(snapshot),
        "--snapshot-workspace", str(tmp_path / "new-chat.sqlite"),
        "--snapshot-library", str(tmp_path / "new-docs.sqlite"),
        "--snapshot-queue", str(tmp_path / "new-queue.sqlite"),
        "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["action"] == "restored"
    assert (tmp_path / "new-chat.sqlite").is_file()


def test_restored_queue_fences_old_device_paths_and_worker_leases(tmp_path: Path) -> None:
    source = tmp_path / "old-notes"
    source.mkdir()
    (source / "old.md").write_text("original local content", encoding="utf-8")
    library = tmp_path / "old-lib.sqlite"
    with OfflineDocumentLibrary(library) as store:
        store.index_directory(source)
    queuefile = tmp_path / "old-queue.sqlite"
    with OfflineIndexQueue(queuefile) as store:
        pending = store.enqueue(source, library)
        snapshot = tmp_path / "queue-backup"
        create_snapshot(snapshot, queue=queuefile)
        # A restored queue must not auto-run a job pointing to this old path.
    recovered = tmp_path / "new-device-queue.sqlite"
    restore_snapshot(snapshot, queue=recovered)
    with OfflineIndexQueue(recovered) as store:
        record = store.get(pending.job_id)
        assert record.state == "cancelled"
        assert store.run_one() is None
        assert record.source == str(source.resolve())
        assert record.library == str(library.resolve())
        assert "restored queue" in record.last_error
    # The original persisted queue is unchanged by a restore.
    with OfflineIndexQueue(queuefile) as original:
        assert original.get(pending.job_id).state == "queued"


def test_restored_running_lease_is_quarantined_even_if_not_expired(tmp_path: Path) -> None:
    _, _, queue = _example(tmp_path)
    with OfflineIndexQueue(queue) as store:
        claim = store._claim()
        assert claim is not None
        job_id = claim[0].job_id
    archive = tmp_path / "busy-queue"
    create_snapshot(archive, queue=queue)
    restored = tmp_path / "busy-queue-restored.sqlite"
    restore_snapshot(archive, queue=restored)
    with OfflineIndexQueue(restored) as store:
        assert store.get(job_id).state == "cancelled"
        assert store.run_one() is None


def test_snapshot_publication_never_clobbers_racing_directory(
    tmp_path: Path, monkeypatch,
) -> None:
    import skeleton.app.offline_snapshot as module

    workspace, _, _ = _example(tmp_path)
    target = tmp_path / "snapshot"
    actual_publish = module._publish_new_snapshot

    def competitor_arrives(stage, destination):
        destination.mkdir()
        (destination / "private.txt").write_text("do not delete", encoding="utf-8")
        return actual_publish(stage, destination)

    monkeypatch.setattr(module, "_publish_new_snapshot", competitor_arrives)
    with pytest.raises(FileExistsError):
        create_snapshot(target, workspace=workspace)
    assert (target / "private.txt").read_text("utf-8") == "do not delete"
    assert sorted(item.name for item in target.iterdir()) == ["private.txt"]


def test_snapshot_manifest_is_last_and_incomplete_publication_is_rejected(
    tmp_path: Path, monkeypatch,
) -> None:
    import skeleton.app.offline_snapshot as module

    workspace, _, _ = _example(tmp_path)
    target = tmp_path / "snapshot"
    original_link = module.os.link
    examined = []

    def reject_final_link(source, destination, *args, **kwargs):
        if Path(source).name == "manifest.json":
            with pytest.raises(OfflineSnapshotError, match="manifest"):
                verify_snapshot(target)
            examined.append(True)
            raise OSError("simulated failure before final manifest")
        return original_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(module.os, "link", reject_final_link)
    with pytest.raises(OSError, match="simulated failure"):
        create_snapshot(target, workspace=workspace)
    assert examined
    assert not target.exists()


def test_failed_multi_file_restore_never_deletes_competing_replacement(
    tmp_path: Path, monkeypatch,
) -> None:
    import skeleton.app.offline_snapshot as module

    workspace, library, _ = _example(tmp_path)
    archive = tmp_path / "snapshot"
    create_snapshot(archive, workspace=workspace, library=library)
    library_destination = tmp_path / "recovered-docs.sqlite"
    workspace_destination = tmp_path / "recovered-chat.sqlite"
    original_link = module.os.link

    def replace_after_first_publish(source, destination, *args, **kwargs):
        if Path(destination) == workspace_destination:
            assert library_destination.exists()
            library_destination.unlink()
            library_destination.write_bytes(b"new concurrent private data")
            raise OSError("simulated competing mutation")
        return original_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(module.os, "link", replace_after_first_publish)
    with pytest.raises(OSError, match="competing mutation"):
        restore_snapshot(
            archive, workspace=workspace_destination,
            library=library_destination,
        )
    assert library_destination.read_bytes() == b"new concurrent private data"
    assert not workspace_destination.exists()
