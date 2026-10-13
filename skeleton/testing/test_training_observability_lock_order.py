"""Inspection cannot invert the locks of actual dataset-fenced checkpoints."""

from __future__ import annotations

import multiprocessing
import threading
import traceback
from datetime import timedelta

import pytest

from skeleton.ai.runtime.training.observability import TrainingObserver
from skeleton.testing.test_training_observability import NOW, _fixture, _train


class _AcquisitionProbe:
    def __init__(self, lock, name, order, attempted):
        self.lock = lock
        self.name = name
        self.order = order
        self.attempted = attempted

    def acquire(self, blocking=True, timeout=-1):
        if threading.current_thread().name == "training-observer-audit":
            self.order.append(self.name)
            self.attempted.set()
        return self.lock.acquire(blocking=blocking, timeout=timeout)

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_exception):
        self.release()


class _ReadAuditConnection:
    """Inspect SQL in Python before entering SQLite's connection mutex."""

    def __init__(self, connection, observer_writes):
        self.connection = connection
        self.observer_writes = observer_writes

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args, **kwargs):
        if threading.current_thread().name == "training-observer-audit":
            verb = statement.lstrip().split(maxsplit=1)[0].upper()
            if verb not in {"SELECT", "BEGIN", "ROLLBACK", "PRAGMA"}:
                self.observer_writes.append(statement)
        return self.connection.execute(statement, *args, **kwargs)


def _concurrent_checkpoint_audit(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path, "reference")
    dataset_lock, training_lock = datasets._lock, runs._lock
    checkpoint_entered = threading.Event()
    observer_attempted = threading.Event()
    order, errors, trained, observed, observer_writes = [], [], [], [], []
    monkeypatch.setattr(
        datasets, "_lock", _AcquisitionProbe(dataset_lock, "dataset", order, observer_attempted)
    )
    monkeypatch.setattr(
        runs, "_lock", _AcquisitionProbe(training_lock, "training", order, observer_attempted)
    )
    real_checkpoint = runs.checkpoint
    first = True

    def paused_checkpoint(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            assert dataset_lock._is_owned()
            checkpoint_entered.set()
            if not observer_attempted.wait(2):
                raise AssertionError("inspector never attempted its first lock")
            if not training_lock.acquire(timeout=1):
                # Release the caller's dataset guard through the exception so
                # the pre-fix lock inversion fails without hanging the test.
                raise AssertionError("inspector blocked a dataset-fenced checkpoint")
            training_lock.release()
        return real_checkpoint(*args, **kwargs)

    monkeypatch.setattr(runs, "checkpoint", paused_checkpoint)

    monkeypatch.setattr(runs, "_db", _ReadAuditConnection(runs._db, observer_writes))
    monkeypatch.setattr(datasets, "_db", _ReadAuditConnection(datasets._db, observer_writes))

    def train():
        try:
            trained.append(_train(datasets, runs, manifest, "reference"))
        except BaseException as exc:  # noqa: BLE001 - Propagate worker failures to the joining test.
            errors.append(exc)

    def inspect():
        try:
            if not checkpoint_entered.wait(2):
                raise AssertionError("actual trainer never reached a fenced checkpoint")
            observed.append(
                TrainingObserver(runs, datasets)
                .snapshot(manifest.run_id, now=NOW + timedelta(seconds=1))
                .as_dict()
            )
        except BaseException as exc:  # noqa: BLE001 - Propagate inspector failures to the joining test.
            errors.append(exc)

    trainer = threading.Thread(target=train, name="actual-training-audit", daemon=True)
    observer = threading.Thread(target=inspect, name="training-observer-audit", daemon=True)
    try:
        observer.start()
        trainer.start()
        trainer.join(timeout=5)
        observer.join(timeout=5)
        assert not trainer.is_alive() and not observer.is_alive(), "concurrent inspection did not quiesce"
        assert errors == []
        assert order[0] == "dataset"
        assert observer_writes == []
        model, artifact = trained[0]
        terminal = runs.latest_checkpoint(manifest.run_id)
        assert runs.state(manifest.run_id) == "completed"
        assert terminal.digest == artifact.checkpoint_digest
        assert terminal.model_digest == model.model_digest
        report = observed[0]
        assert report["source"]["current_training_admission"] is True
        assert report["checkpoints"]
        latest = report["checkpoints"][-1]
        assert latest["semantic_validation"] == "verified_exact_corpus"
        assert latest["usage"]["documents"] == latest["cursor"]["document_index"]
        if report["state"] == "completed":
            assert latest["finished"] is True
            assert latest["checkpoint_digest"] == terminal.digest
    finally:
        # A future application deadlock must not block SQLite teardown. The
        # supervising process terminates the isolated audit if workers remain.
        if not trainer.is_alive() and not observer.is_alive():
            runs.close()
            datasets.close()


def _audit_process(tmp_path, channel):
    try:
        with pytest.MonkeyPatch.context() as monkeypatch:
            _concurrent_checkpoint_audit(tmp_path, monkeypatch)
        channel.send(None)
    except BaseException:  # noqa: BLE001 - Send child assertion and worker failures to the parent.
        channel.send(traceback.format_exc())
    finally:
        channel.close()


def test_actual_checkpoint_and_inspection_share_dataset_then_training_lock_order(tmp_path):
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_audit_process, args=(tmp_path, writer))
    try:
        process.start()
        writer.close()
        process.join(timeout=20)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            pytest.fail("concurrent training inspection failed to quiesce within the audit deadline")
        assert process.exitcode == 0
        assert reader.poll(1), "isolated training audit returned no result"
        failure = reader.recv()
        assert failure is None, failure
    finally:
        if process.pid is not None and process.is_alive():
            process.kill()
            process.join(timeout=2)
        reader.close()
        writer.close()
        if process.pid is not None and not process.is_alive():
            process.close()
