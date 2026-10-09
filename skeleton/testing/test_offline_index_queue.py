"""Offline document ingestion queue: restart, contention, retries and CLI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.app.offline_index_queue import (
    OfflineIndexQueue, OfflineQueueError, MAX_ATTEMPTS,
)
from skeleton.app.offline_library import OfflineDocumentLibrary
from skeleton.app.offline_cli import main as offline_main
from skeleton.app.cli import run_app_cli


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    (root / "engine.md").write_text(
        "Local physics replay and deterministic frame state.", encoding="utf-8",
    )
    return root


def test_queue_durable_across_restart_and_indexed_content_searchable(
    tmp_path: Path,
) -> None:
    source = _root(tmp_path)
    index = tmp_path / "knowledge.sqlite"
    queuefile = tmp_path / "queue.sqlite"
    with OfflineIndexQueue(queuefile) as queue:
        first = queue.enqueue(source, index)
        assert first.state == "queued"
        assert len(first.job_id) == 32
        assert queue.enqueue(source, index).job_id == first.job_id
        assert queue.list_jobs()[0].job_id == first.job_id
    with OfflineIndexQueue(queuefile) as resumed:
        assert resumed.get(first.job_id).attempts == 0
        completed = resumed.run_one()
        assert completed is not None
        assert completed.state == "completed"
        assert completed.attempts == 1
        assert completed.result["indexed_files"] == 1
        assert resumed.run_one() is None
    with OfflineDocumentLibrary(index) as library:
        assert library.search("physics replay")[0].relative_path == "engine.md"


def test_enqueue_requires_existing_trusted_directory_and_separate_library(
    tmp_path: Path,
) -> None:
    source = _root(tmp_path)
    queuefile = tmp_path / "queue.sqlite"
    with OfflineIndexQueue(queuefile) as queue:
        with pytest.raises(OfflineQueueError, match="must differ"):
            queue.enqueue(source, queuefile)
        with pytest.raises((OfflineQueueError, RuntimeError), match="directory"):
            queue.enqueue(tmp_path / "missing", tmp_path / "lib.sqlite")


def test_cancel_and_explicit_retry_are_state_fenced(tmp_path: Path) -> None:
    source = _root(tmp_path)
    qfile = tmp_path / "queue.sqlite"
    with OfflineIndexQueue(qfile) as queue:
        job = queue.enqueue(source, tmp_path / "index.sqlite")
        cancelled = queue.cancel(job.job_id)
        assert cancelled.state == "cancelled"
        with pytest.raises(OfflineQueueError, match="only queued"):
            queue.cancel(job.job_id)
        with pytest.raises(OfflineQueueError, match="only terminal failed"):
            queue.retry(job.job_id)
        assert queue.run_one() is None


def test_bounded_retries_and_no_false_completed_result(tmp_path: Path) -> None:
    source = _root(tmp_path)
    qfile = tmp_path / "queue.sqlite"
    with OfflineIndexQueue(qfile) as queue:
        job = queue.enqueue(source, tmp_path / "lib.sqlite")
        # The user-selected input becomes unavailable *after* being queued.
        (source / "engine.md").unlink()
        source.rmdir()
        results = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            with queue._lock:
                queue._db.execute(
                    "UPDATE offline_index_jobs SET next_due_at=0 WHERE job_id=?",
                    (job.job_id,),
                )
            outcome = queue.run_one()
            assert outcome is not None
            results.append(outcome)
            assert outcome.attempts == attempt
            assert outcome.result is None
        assert [item.state for item in results] == [
            "queued", "queued", "failed",
        ]
        assert queue.run_one() is None
        assert queue.retry(job.job_id).state == "queued"
        assert queue.get(job.job_id).attempts == 0


def test_expired_lease_is_reclaimed_and_old_worker_fenced(tmp_path: Path) -> None:
    source = _root(tmp_path)
    db = tmp_path / "queue.sqlite"
    with OfflineIndexQueue(db) as worker_one:
        job = worker_one.enqueue(source, tmp_path / "index.sqlite")
        claimed = worker_one._claim()
        assert claimed is not None
        job_snapshot, stale_token = claimed
        assert job_snapshot.job_id == job.job_id
        worker_one._db.execute(
            "UPDATE offline_index_jobs SET lease_until=0 WHERE job_id=?",
            (job.job_id,),
        )
        with OfflineIndexQueue(db) as worker_two:
            delivered = worker_two.run_one()
            assert delivered is not None and delivered.state == "completed"
            assert delivered.attempts == 2
        with pytest.raises(OfflineQueueError, match="lease ownership lost"):
            worker_one._finish(job_snapshot, stale_token, result={"indexed_files": 0})
        assert worker_one.get(job.job_id).result["indexed_files"] == 1


def test_expired_max_attempt_job_becomes_failed_without_database_violation(
    tmp_path: Path,
) -> None:
    source = _root(tmp_path)
    with OfflineIndexQueue(tmp_path / "queue.sqlite") as queue:
        job = queue.enqueue(source, tmp_path / "lib.sqlite")
        queue._db.execute(
            "UPDATE offline_index_jobs SET state='running', attempts=?, "
            "lease_until=0, lease_token='stale' WHERE job_id=?",
            (MAX_ATTEMPTS, job.job_id),
        )
        assert queue.run_one() is None
        state = queue.get(job.job_id)
        assert state.state == "failed"
        assert "expired worker lease" in state.last_error


def test_rejects_untrusted_path_and_unbounded_drain(tmp_path: Path) -> None:
    source = _root(tmp_path)
    with OfflineIndexQueue(tmp_path / "queue.sqlite") as queue:
        with pytest.raises(OfflineQueueError, match="batch"):
            queue.drain(limit=21)
        with pytest.raises(OfflineQueueError, match="id"):
            queue.get("../../../somewhere")
        with pytest.raises(OfflineQueueError, match="only queued"):
            queue.cancel("a" * 32)
        link = tmp_path / "link"
        try:
            link.symlink_to(source, target_is_directory=True)
        except OSError:
            pytest.skip("symlink unsupported")
        with pytest.raises(RuntimeError, match="directory"):
            queue.enqueue(link, tmp_path / "lib.sqlite")


def test_local_console_queue_and_app_cli_share_same_durable_state(
    tmp_path: Path, capsys,
) -> None:
    source = _root(tmp_path)
    queuefile = tmp_path / "queue.sqlite"
    index = tmp_path / "knowledge.sqlite"
    assert offline_main([
        "--queue-db", str(queuefile), "--enqueue-dir", str(source),
        "--queue-library", str(index), "--json",
    ]) == 0
    first = json.loads(capsys.readouterr().out)
    job_id = first["enqueued"]["job_id"]
    assert run_app_cli([
        "local-ai", "--queue-db", str(queuefile),
        "--run-queue", "--queue-status", "--json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["processed"][0]["job_id"] == job_id
    assert result["processed"][0]["state"] == "completed"
    assert result["jobs"][0]["state"] == "completed"
    assert offline_main([
        "--library", str(index), "--search", "physics", "--json",
    ]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits["results"][0]["relative_path"] == "engine.md"


def test_cli_refuses_model_or_missing_library_in_queue_mode(
    tmp_path: Path, capsys,
) -> None:
    source = _root(tmp_path)
    assert offline_main([
        "--queue-db", str(tmp_path / "queue.sqlite"),
        "--enqueue-dir", str(source),
    ]) == 2
    assert offline_main([
        "--queue-db", str(tmp_path / "queue.sqlite"),
        "--run-queue", "--model", "no-model.json",
    ]) == 2
    assert offline_main([
        "--queue-db", str(tmp_path / "queue.sqlite"),
        "--run-queue", "--drain-limit", "100",
    ]) == 2
    assert capsys.readouterr().out == ""


def test_stale_worker_cannot_commit_index_data_after_lease_reclaimed(
    tmp_path: Path, monkeypatch,
) -> None:
    source = _root(tmp_path)
    index_path = tmp_path / "indexed.sqlite"
    with OfflineIndexQueue(tmp_path / "queue.sqlite") as queue:
        job = queue.enqueue(source, index_path)
        original = OfflineDocumentLibrary.index_directory

        def simulate_reclaimed_lease(library, directory, *, before_commit=None):
            assert before_commit is not None
            # Adversarial interleaving: worker B owns the lease while worker
            # A is about to publish its staged FTS documents.
            queue._db.execute(
                "UPDATE offline_index_jobs "
                "SET lease_token=?, lease_until=? WHERE job_id=?",
                ("f" * 32, 9999999999.0, job.job_id),
            )
            return original(library, directory, before_commit=before_commit)

        monkeypatch.setattr(
            OfflineDocumentLibrary, "index_directory",
            simulate_reclaimed_lease,
        )
        with pytest.raises(OfflineQueueError, match="ownership lost"):
            queue.run_one()
        monkeypatch.setattr(OfflineDocumentLibrary, "index_directory", original)
        with OfflineDocumentLibrary(index_path) as documents:
            assert documents.count() == 0
        assert queue.get(job.job_id).state == "running"


def test_expired_unreclaimed_worker_does_not_publish_document_index(
    tmp_path: Path, monkeypatch,
) -> None:
    source = _root(tmp_path)
    index_path = tmp_path / "indexed.sqlite"
    with OfflineIndexQueue(tmp_path / "queue.sqlite") as queue:
        job = queue.enqueue(source, index_path)
        original = OfflineDocumentLibrary.index_directory

        def simulate_expiration(library, directory, *, before_commit=None):
            queue._db.execute(
                "UPDATE offline_index_jobs SET lease_until=0 WHERE job_id=?",
                (job.job_id,),
            )
            return original(library, directory, before_commit=before_commit)

        monkeypatch.setattr(
            OfflineDocumentLibrary, "index_directory", simulate_expiration,
        )
        completed = queue.run_one()
        assert completed is not None
        assert completed.state == "queued"
        assert completed.result is None
        with OfflineDocumentLibrary(index_path) as documents:
            assert documents.count() == 0
