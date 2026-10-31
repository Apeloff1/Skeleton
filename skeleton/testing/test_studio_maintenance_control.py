"""Exercise maintenance custody and recovery without providers or model work."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import threading
from time import time_ns
from types import SimpleNamespace

import pytest

from skeleton.intelligence.runtime_control import RuntimeOptimizationControl
from skeleton.jeeves.ai.idle_learning_runtime import IdleRuntimeError
from skeleton.jeeves.ai.idle_learning_scheduler import (
    HostIdleTelemetry,
    IdleLearningPolicy,
    IdleWorkKind,
)
from skeleton.jeeves.ai import studio_maintenance as maintenance


def _telemetry():
    now = time_ns()
    return (
        HostIdleTelemetry(
            observed_at_ns=now,
            last_user_activity_ns=0,
            serving_pressure_ppm=0,
            cpu_free_ppm=1_000_000,
            memory_free_ppm=1_000_000,
            gpu_free_ppm=1_000_000,
            active_background_workers=0,
            pending_interactive_requests=0,
            power_saving=False,
            online=False,
            host_observation_digest="a" * 64,
        ),
        now,
    )


@pytest.fixture
def controllers(tmp_path):
    owned = []

    def create(callback=None, *, policy=None, **kwargs):
        controller = maintenance.create_studio_maintenance(
            store_path=tmp_path / "execution.sqlite3",
            telemetry_probe=_telemetry,
            host_authorize=lambda assignment, intent, task: (
                assignment.scope_id == task.scope_id == "tenant-test"
                and assignment.source_digest == task.source_digest
                and assignment.kind is task.kind
            ),
            callbacks={
                IdleWorkKind.CACHE_CLEANUP: maintenance.MaintenanceHandler(
                    callback or (lambda task, checkpoint: {"cleaned": 1}), retry_safe=True
                )
            },
            idle_policy=IdleLearningPolicy(minimum_idle_ns=0),
            policy=policy or maintenance.StudioMaintenancePolicy(enabled=True),
            **kwargs,
        )
        owned.append(controller)
        return controller

    yield create
    for controller in reversed(owned):
        controller.close()


def _enqueue(controller, key="one"):
    return controller.enqueue(
        kind=IdleWorkKind.CACHE_CLEANUP,
        scope_id="tenant-test",
        source_digest="b" * 64,
        idempotency_key=key,
        payload={"tenant_id": "test"},
    )["task_id"]


def _task(controller, task_id):
    return next(row for row in controller.snapshot()["recent_tasks"] if row["task_id"] == task_id)


def test_canonical_json_keeps_exact_digest_bytes_and_utf8_budget():
    value = {"text": "snowman \u2603 and music \U0001d11e", "numbers": [0, -1, 0.25]}
    expected = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert maintenance._canonical(value, maximum_bytes=len(expected)) == expected
    with pytest.raises(IdleRuntimeError, match="chunk budget"):
        maintenance._canonical(value, maximum_bytes=len(expected) - 1)


def test_huge_mapping_is_rejected_before_iteration_or_copy():
    class WideMapping(Mapping):
        def __len__(self):
            return 10_000_000

        def __iter__(self):
            raise AssertionError("wide mapping must not be copied")

        def __getitem__(self, key):
            raise AssertionError("wide mapping must not be read")

    with pytest.raises(IdleRuntimeError, match="chunk budget"):
        maintenance.MaintenanceResult(output=WideMapping())


@pytest.mark.parametrize(
    "value", [{2: "numeric key"}, {"nested": {10: "numeric key"}}, {"value": float("nan")}]
)
def test_invalid_json_cannot_enter_replay_receipts(value):
    with pytest.raises(IdleRuntimeError):
        maintenance.MaintenanceResult(output=value)


def test_cyclic_and_deep_results_are_bounded_before_encoding():
    cycle = []
    cycle.append(cycle)
    with pytest.raises(IdleRuntimeError, match="finite JSON"):
        maintenance.MaintenanceResult(output={"cycle": cycle})
    nested = {}
    for _ in range(70):
        nested = {"nested": nested}
    with pytest.raises(IdleRuntimeError, match="nesting budget"):
        maintenance.MaintenanceResult(output=nested)


def test_result_and_continuation_detach_original_callback_aliases():
    output = {"records": [{"value": 1}]}
    cursor = {"page": [2]}
    result = maintenance.MaintenanceResult(output=output, complete=False, continuation=cursor)
    before = maintenance.StudioMaintenanceController._result_json(result)
    output["records"][0]["value"] = 999
    cursor["page"].append(3)
    assert maintenance.StudioMaintenanceController._result_json(result) == before
    with pytest.raises(TypeError):
        result.output["extra"] = True


def test_new_owner_is_non_admitting_until_first_host_sync(controllers):
    controller = controllers()
    before = controller.snapshot()
    assert before["ownership"]["state"] == "initializing"
    assert controller.synchronize_foreground(2) is None
    after = controller.snapshot()
    assert after["ownership"]["state"] == "live"
    assert after["ownership"]["foreground_requests"] == 2
    assert controller.tick()["processed"] == 0


def test_malformed_acknowledgement_retries_only_ack_not_completed_work(controllers):
    calls = []
    acknowledged = False

    def handler(task, checkpoint):
        calls.append(task.continuation_id)
        checkpoint()
        return {"cleaned": 1}

    def acknowledge(task, result, receipt):
        return {"acknowledged": True if acknowledged else "true"}

    controller = controllers(handler, after_verified_chunk=acknowledge)
    task_id = _enqueue(controller)
    assert controller.tick()["processed"] == 1
    assert _task(controller, task_id)["state"] == "completed"
    pending = controller.snapshot()["acknowledgements"]
    assert pending["pending"] == 1
    assert pending["failed_attempts"] == 1
    assert pending["next_retry_ns"] > 0
    acknowledged = True
    with controller._executor._lock:
        controller._executor._db.execute("UPDATE jeeves_idle_maintenance_chunk SET next_ack_ns=0")
    assert controller.tick()["processed"] == 0
    assert controller.snapshot()["acknowledgements"]["pending"] == 0
    assert len(calls) == 1
    controller._executor.history_head(verify=True)


def test_unverified_completed_result_keeps_host_retry_target_through_compaction(controllers):
    calls = []

    def handler(task, checkpoint):
        calls.append(task.task_id)
        return {"cleaned": 1}

    controller = controllers(
        handler,
        policy=replace(
            maintenance.StudioMaintenancePolicy(enabled=True),
            maximum_retained_tasks=1,
            maximum_consecutive_failures=1,
        ),
    )
    retained_id = _enqueue(controller, "retained")
    verifier = controller._executor._verify

    def unavailable_verifier(*args):
        raise RuntimeError("verification temporarily unavailable")

    controller._executor._verify = unavailable_verifier
    assert controller.tick()["processed"] == 0
    assert _task(controller, retained_id)["state"] == "failed"
    controller._executor._verify = verifier
    for key in ("ordinary-one", "ordinary-two"):
        _enqueue(controller, key)
        assert controller.tick()["processed"] == 1
    assert _task(controller, retained_id)["state"] == "failed"
    retry = controller.retry_failed(
        task_id=retained_id, scope_id="tenant-test", source_digest="b" * 64, expected_attempts=1
    )
    assert retry["retained_result"] is True
    assert controller.tick()["processed"] == 1
    assert calls.count(retained_id) == 1
    assert _task(controller, retained_id)["state"] == "completed"
    controller._executor.history_head(verify=True)


def test_close_waits_for_physical_callback_drain_and_releases_exact_leases(controllers, tmp_path):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    failures = []

    def handler(task, checkpoint):
        entered.set()
        if not release.wait(3):
            raise RuntimeError("callback release timed out")
        return {"cleaned": 1}

    controller = controllers(handler)
    _enqueue(controller)

    def run_tick():
        try:
            controller.tick()
        except BaseException as exc:
            failures.append(exc)

    def run_close():
        try:
            controller.close()
        except BaseException as exc:
            failures.append(exc)
        finally:
            closed.set()

    worker = threading.Thread(target=run_tick)
    closer = threading.Thread(target=run_close)
    worker.start()
    try:
        assert entered.wait(2)
        closer.start()
        assert not closed.wait(0.05)
    finally:
        release.set()
        worker.join(3)
        if closer.ident is not None:
            closer.join(3)
    assert not worker.is_alive() and not closer.is_alive()
    assert failures == []
    with sqlite3.connect(tmp_path / "execution.sqlite3") as db:
        assert db.execute("SELECT state,physical_tasks FROM jeeves_idle_maintenance_owner").fetchall() == [
            ("drained", 0)
        ]
        assert db.execute(
            "SELECT COUNT(*) FROM jeeves_idle_maintenance_lease WHERE state='held'"
        ).fetchone() == (0,)


def test_drain_proof_runs_outside_locks_and_cas_rejects_changed_presence(controllers):
    observed = []
    controller = None

    def prove(info):
        # A separate thread must be able to inspect using both local locks
        # while this host callback is still on the repair call stack.
        def observe():
            with controller._state_lock, controller._executor._lock:
                db = controller._executor._db
                db.execute(
                    "UPDATE jeeves_idle_maintenance_owner SET heartbeat_ns=heartbeat_ns+1 WHERE owner_id=?",
                    (info["owner_id"],),
                )
                observed.append(info["owner_id"])

        thread = threading.Thread(target=observe)
        thread.start()
        thread.join(1)
        return not thread.is_alive()

    foreign = controllers(owner_id="foreign-owner")
    foreign.heartbeat()
    controller = controllers(host_confirm_drained=prove)
    with controller._executor._lock:
        controller._executor._db.execute(
            "UPDATE jeeves_idle_maintenance_owner SET heartbeat_ns=0,process_namespace='unavailable' WHERE owner_id=?",
            (foreign._identity["owner_id"],),
        )
    controller._retire_stale_presence(controller.policy)
    assert observed == [foreign._identity["owner_id"]]
    assert foreign.snapshot()["ownership"]["state"] == "live"
    assert controller.snapshot()["quiescence"]["last_presence_repair"]["retired"] == 0


def test_expired_lease_does_not_transfer_live_physical_work(controllers):
    entered, release = threading.Event(), threading.Event()
    foreign_calls, local_calls, failures = [], [], []

    def foreign_handler(task, checkpoint):
        foreign_calls.append(task.task_id)
        entered.set()
        if not release.wait(3):
            raise RuntimeError("foreign callback release timed out")
        return {"cleaned": 1}

    foreign = controllers(foreign_handler, owner_id="physical-foreign-owner")
    local = controllers(lambda task, checkpoint: local_calls.append(task.task_id) or {"cleaned": 1})
    local.heartbeat()
    task_id = _enqueue(foreign)

    def invoke_foreign():
        try:
            foreign.tick()
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=invoke_foreign)
    worker.start()
    try:
        assert entered.wait(2)
        with local._executor._lock:
            local._executor._db.execute(
                "UPDATE jeeves_idle_maintenance_task SET lease_until_ns=0 WHERE task_id=?", (task_id,)
            )
            local._executor._db.execute(
                "UPDATE jeeves_idle_maintenance_lease SET lease_until_ns=0 WHERE task_id=?", (task_id,)
            )
        assert local.tick()["processed"] == 0
        row = _task(local, task_id)
        assert row["state"] == "running"
        assert row["owner_id"] == foreign._identity["owner_id"]
        assert row["recovery_reason"] == "recovery_blocked_owner_alive_or_unknown"
        assert foreign.snapshot()["ownership"]["physical_tasks"] == 1
        assert local_calls == []
    finally:
        release.set()
        worker.join(3)
    assert failures == [] and not worker.is_alive()
    assert foreign_calls == [task_id]
    assert _task(local, task_id)["state"] == "completed"


def _control_for_initialization(path):
    control = RuntimeOptimizationControl.__new__(RuntimeOptimizationControl)
    control.repository = SimpleNamespace(path=path)
    control._activity_lock = threading.Lock()
    control._foreground = 0
    control._maintenance = None
    control._maintenance_coordination_error = None
    return control


def test_runtime_control_preserves_literal_execution_database_path(tmp_path, monkeypatch):
    seen = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        maintenance,
        "create_studio_maintenance",
        lambda **kwargs: (
            seen.append(kwargs["store_path"]) or SimpleNamespace(synchronize_foreground=lambda count: None)
        ),
    )
    control = _control_for_initialization("~/execution.sqlite3")
    control._initialize_maintenance()
    assert seen == [tmp_path / "~" / "execution.sqlite3"]


def test_runtime_control_does_not_publish_before_atomic_foreground_sync(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    failures = []

    class Presence:
        foreground = 0

        def synchronize_foreground(self, count):
            entered.set()
            assert release.wait(2)
            self.foreground = count

        def foreground_started(self):
            self.foreground += 1

    presence = Presence()
    monkeypatch.setattr(maintenance, "create_studio_maintenance", lambda **kwargs: presence)
    control = _control_for_initialization(Path("/execution.sqlite3"))

    def initialize():
        try:
            control._initialize_maintenance()
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=initialize)
    worker.start()
    try:
        assert entered.wait(2)
        assert control._maintenance is None
        acquired = control._activity_lock.acquire(blocking=False)
        if acquired:
            control._activity_lock.release()
        assert not acquired
    finally:
        release.set()
        worker.join(3)
    assert failures == [] and not worker.is_alive()
    control.foreground_started()
    assert control._foreground == presence.foreground == 1


def test_runtime_control_serializes_foreground_edge_delivery():
    entered, release = threading.Event(), threading.Event()
    failures = []

    class Presence:
        foreground = 0
        policy = SimpleNamespace(enabled=False)

        def foreground_started(self):
            entered.set()
            assert release.wait(2)
            self.foreground += 1

        def foreground_finished(self):
            self.foreground = max(0, self.foreground - 1)

    presence = Presence()
    control = _control_for_initialization("/execution.sqlite3")
    control._maintenance = presence
    control._closed = False

    def begin():
        try:
            control.foreground_started()
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=begin)
    finisher = threading.Thread(target=lambda: control.foreground_finished(SimpleNamespace()))
    worker.start()
    try:
        assert entered.wait(2)
        acquired = control._activity_lock.acquire(blocking=False)
        if acquired:
            control._activity_lock.release()
        assert not acquired
        finisher.start()
    finally:
        release.set()
        worker.join(3)
        if finisher.ident is not None:
            finisher.join(3)
    assert failures == [] and not worker.is_alive() and not finisher.is_alive()
    assert control._foreground == presence.foreground == 0
