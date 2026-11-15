"""App bridge tests: simulated CPU probe and owner, no device certification."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.app.offline_dispatch_bridge import OfflineAdaptiveDispatchService
from skeleton.ai.model_runtime.fair_stream_dispatch import (
    DispatchDeferred, DispatchUncertain,
)
from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_custody import sign_execution_result
from skeleton.ai.model_runtime.fair_stream_queue import (
    MeasuredStreamBudget, StreamRequest,
)
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase

C, E, SESSION = b"c" * 32, b"e" * 32, "a" * 32


class ExternalAnchor:
    """In-memory test double only; NOT an independent durable anchor."""
    def __init__(self):
        self.state = None

    def initialize(self, *, generation, digest):
        if self.state is not None:
            raise ValueError("already initialized")
        self.state = generation, digest

    def read(self):
        if self.state is None:
            raise ValueError("missing external anchor")
        return self.state

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.state != (expected_generation, expected_digest):
            raise ValueError("stale CAS")
        self.state = generation, digest


class SimulatedDurableOwner:
    def __init__(self):
        self.calls = 0

    def execute_and_commit(self, permit, state):
        self.calls += 1
        return sign_execution_result(
            execution_key=E, session_id=SESSION,
            generation=state["generation"],
            checkpoint_digest=state["checkpoint_digest"],
            lease_id=permit.lease_id,
            consumed_tokens=permit.tokens, result_digest="f" * 64,
        )


def install_probe(monkeypatch, *, hold=False):
    def sample(self, *, token_budget, storage_path):
        return (
            MeasuredStreamBudget(
                4096, 1024, token_budget, 1, 0, hold, "os_probe",
            ),
            {
                "measurement": "os_probe",
                "gpu_device_qualified": False,
                "physical_memory_reserved": False,
                "auxiliary_telemetry_incomplete": True,
                "schema": "skeleton.ai.live-stream-pressure.v1",
                "cross_process_admission_guaranteed": False,
                "thermal_trip_measured": True,
                "cgroup_swap_spill_allowed": True,
                "cgroup_swap_limit_measured": True,
                "cgroup_memory_limit_measured": True,
                "holds": {
                    "thermal": False, "cgroup_high": False, "cgroup_oom": False,
                    "cgroup_memory": False, "cgroup_swap_spill": False,
                    "io": False, "cpu_throttle": False, "swap_churn": False,
                    "reclaim": False, "disk_reserve": False,
                },
            },
        )
    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)


def make(*, connection=None, anchor=None, owner=None, bootstrap=True):
    return OfflineAdaptiveDispatchService.from_trusted_handles(
        connection=connection or sqlite3.connect(":memory:"),
        custody_key=C, execution_key=E, session_id=SESSION,
        watermark=anchor or ExternalAnchor(),
        owner=owner or SimulatedDurableOwner(), storage_path=".",
        bootstrap=bootstrap,
    )


def request():
    return StreamRequest("request", "tenant", InferencePhase.PREFILL, 32, 4)


def test_app_user_flow_uses_real_canonical_state_and_signed_receipt(monkeypatch):
    install_probe(monkeypatch)
    owner = SimulatedDurableOwner()
    app = make(owner=owner)
    assert app.status().generation == 0
    assert app.submit(request()).generation == 1
    receipt = app.execute_next(token_budget=32)
    assert receipt["state"] == "durably_acknowledged"
    assert receipt["generation"] == 3
    assert receipt["gpu_device_qualified"] is False
    assert app.status().pending_leases == 0
    assert owner.calls == 1


def test_thermal_hold_denies_app_execution(monkeypatch):
    install_probe(monkeypatch, hold=True)
    owner = SimulatedDurableOwner()
    app = make(owner=owner)
    app.submit(request())
    with pytest.raises(DispatchDeferred):
        app.execute_next(token_budget=32)
    assert owner.calls == 0


def test_restart_does_not_implicitly_reset_session(monkeypatch, tmp_path):
    install_probe(monkeypatch)
    path = tmp_path / "trusted-by-test.db"
    anchor = ExternalAnchor()
    conn = sqlite3.connect(path)
    app = make(connection=conn, anchor=anchor)
    app.submit(request())
    conn.close()
    recovered = make(
        connection=sqlite3.connect(path), anchor=anchor, bootstrap=False,
    )
    assert recovered.status().generation == 1
    with pytest.raises(ValueError, match="already initialized"):
        make(
            connection=sqlite3.connect(path), anchor=anchor, bootstrap=True,
        )


def test_pending_restart_is_not_auto_reexecuted(monkeypatch, tmp_path):
    install_probe(monkeypatch)
    path = tmp_path / "pending.db"
    anchor = ExternalAnchor()
    conn = sqlite3.connect(path)
    app = make(connection=conn, anchor=anchor)
    app.submit(request())
    permits, _ = app._guard.plan_live(token_budget=32)
    assert permits
    conn.close()
    recovered = make(
        connection=sqlite3.connect(path), anchor=anchor, bootstrap=False,
    )
    assert recovered.status().pending_leases == 1
    assert recovered.status().execution_uncertain is True
    with pytest.raises(DispatchUncertain, match="pending"):
        recovered.execute_next(token_budget=32)
    with pytest.raises(DispatchUncertain, match="pending"):
        recovered.submit(StreamRequest("second", "tenant", InferencePhase.PREFILL, 4, 4))
    with pytest.raises(DispatchUncertain, match="pending"):
        recovered.cancel("request")


def test_status_excludes_keys_and_raw_checkpoint(monkeypatch):
    install_probe(monkeypatch)
    app = make()
    status = app.status()
    assert set(status.__dataclass_fields__) == {
        "schema", "generation", "pending_leases",
        "quarantined", "execution_uncertain",
    }
    assert not status.quarantined

def test_bridge_resumes_same_unstarted_permit_after_pressure_deferral(monkeypatch):
    owner = SimulatedDurableOwner()
    app = make(owner=owner)
    install_probe(monkeypatch)
    sample = LiveStreamBudgetSampler.sample
    readings = iter((0, 980_000, 0))
    calls = []

    def observed(self, *, token_budget, storage_path):
        calls.append(token_budget)
        _, evidence = sample(self, token_budget=token_budget, storage_path=storage_path)
        return MeasuredStreamBudget(4096, 1024, token_budget, 1, next(readings), False, "os_probe"), evidence

    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", observed)
    app.submit(request())
    with pytest.raises(DispatchDeferred, match="fresh pressure"):
        app.execute_next(token_budget=32)
    pending = app.status()
    assert pending.generation == 2 and pending.pending_leases == 1
    assert not pending.execution_uncertain and owner.calls == 0
    issued = next(iter(app._guard._issued.values()))
    with pytest.raises(DispatchDeferred, match="original planning"):
        app.execute_next(token_budget=64)
    assert calls == [32, 32]
    result = app.execute_next(token_budget=32)
    assert result["generation"] == 3
    assert result["lease_id"] == issued.lease_id
    assert owner.calls == 1 and calls == [32, 32, 32]
    assert app.status().pending_leases == 0


def test_bridge_reports_execution_preflight_observation_not_initial_plan(monkeypatch):
    install_probe(monkeypatch)
    sample = LiveStreamBudgetSampler.sample
    readings = iter((250_000, 100_000))

    def observed(self, *, token_budget, storage_path):
        _, evidence = sample(self, token_budget=token_budget, storage_path=storage_path)
        return MeasuredStreamBudget(4096, 1024, token_budget, 1, next(readings), False, "os_probe"), evidence

    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", observed)
    app = make()
    app.submit(request())
    result = app.execute_next(token_budget=32)
    assert result["executed"] is True
    assert result["observation"]["pressure_ppm"] == 100_000


def test_bridge_never_resumes_owner_after_uncertain_execution(monkeypatch):
    install_probe(monkeypatch)

    class FailingOwner(SimulatedDurableOwner):
        def execute_and_commit(self, permit, state):
            self.calls += 1
            raise OSError("unknown outcome")

    owner = FailingOwner()
    app = make(owner=owner)
    app.submit(request())
    with pytest.raises(DispatchUncertain, match="do not re-execute"):
        app.execute_next(token_budget=32)
    assert app.status().execution_uncertain
    with pytest.raises(DispatchUncertain, match="reconciliation"):
        app.execute_next(token_budget=32)
    assert owner.calls == 1


def test_owner_reentrant_dispatch_cannot_execute_again(monkeypatch):
    install_probe(monkeypatch)
    owner = SimulatedDurableOwner()
    app = make(owner=owner)
    original = owner.execute_and_commit

    def execute(permit, state):
        assert app.status().execution_uncertain
        with pytest.raises(DispatchUncertain, match="reconciliation"):
            app.execute_next(token_budget=32)
        with pytest.raises(DispatchUncertain, match="reconciliation"):
            app._guard.execute_once(permit)
        return original(permit, state)

    monkeypatch.setattr(owner, "execute_and_commit", execute)
    app.submit(request())
    assert app.execute_next(token_budget=32)["executed"]
    assert owner.calls == 1
    assert not app.status().execution_uncertain


def test_invalid_bootstrap_rejected_before_schema_creation():
    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(ValueError, match="bootstrap boolean"):
            OfflineAdaptiveDispatchService.from_trusted_handles(
                connection=connection, custody_key=C, execution_key=E,
                session_id=SESSION, watermark=ExternalAnchor(),
                owner=SimulatedDurableOwner(), storage_path=".", bootstrap=1,
            )
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone() == (0,)
    finally:
        connection.close()


def test_private_database_retains_exact_handle_and_denies_closed_custody(tmp_path):
    import os
    from skeleton.ai.model_runtime.fair_stream_session import CustodyQuarantined

    if os.name != "posix":
        pytest.skip("private POSIX SQLite unavailable")
    directory = tmp_path / "custody"
    directory.mkdir(mode=0o700)
    service, handle = OfflineAdaptiveDispatchService.from_private_database(
        directory=directory, custody_key=C, execution_key=E,
        session_id=SESSION, watermark=ExternalAnchor(),
        owner=SimulatedDurableOwner(), storage_path=".", bootstrap=True,
    )
    try:
        assert service._session._store._private_handle is handle
        assert service.status().generation == 0
    finally:
        handle.close()
    with pytest.raises(CustodyQuarantined):
        service.status()

def test_contended_app_operations_defer_before_any_database_access(monkeypatch):
    from threading import Event, Thread

    app = make()
    entered, release = Event(), Event()

    def holder():
        with app._guard._lock:
            entered.set()
            release.wait(5)

    thread = Thread(target=holder, daemon=True)
    thread.start()
    try:
        assert entered.wait(5)

        def forbidden(*args, **kwargs):
            pytest.fail("contended app operation accessed custody")

        monkeypatch.setattr(app._session, "verify", forbidden)
        for operation in (
            app.status,
            lambda: app.submit(request()),
            lambda: app.cancel("request", tenant_id="tenant"),
            lambda: app.cancel_unstarted("request", tenant_id="tenant"),
            lambda: app.execute_next(token_budget=32),
        ):
            with pytest.raises(DispatchDeferred, match="another app dispatch"):
                operation()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()


def test_submit_status_uses_exact_mutation_without_second_observation(monkeypatch):
    app = make()
    submit = app._guard.submit

    def mutate(request):
        state = submit(request)

        def forbidden(*args, **kwargs):
            pytest.fail("status reread custody after completed submit")

        monkeypatch.setattr(app._session, "verify", forbidden)
        return state

    monkeypatch.setattr(app._guard, "submit", mutate)
    status = app.submit(request())
    assert status.generation == 1
    assert status.pending_leases == 0
    assert not status.execution_uncertain

@pytest.mark.parametrize("key", [b"short", C, E, "not-bytes", b"x" * 129])
def test_invalid_operator_key_never_bootstraps_custody(key):
    connection = sqlite3.connect(":memory:")
    anchor = ExternalAnchor()
    try:
        with pytest.raises(ValueError, match="independent operator recovery key"):
            OfflineAdaptiveDispatchService.from_trusted_handles(
                connection=connection, custody_key=C, execution_key=E,
                session_id=SESSION, watermark=anchor,
                owner=SimulatedDurableOwner(), storage_path=".", bootstrap=True,
                operator_recovery_key=key,
            )
        assert anchor.state is None
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    finally:
        connection.close()


def test_preparation_callback_cannot_reenter_app_dispatch(monkeypatch):
    app = make()
    original = app._session.verify()

    def prepare(item):
        assert app.status().execution_uncertain
        with pytest.raises(DispatchUncertain):
            app.submit(request())
        with pytest.raises(DispatchUncertain):
            app.execute_next(token_budget=32)
        return item

    monkeypatch.setattr(app._guard, "_prepare_request", prepare)
    assert app.submit(request()).generation == original["generation"] + 1
    assert not app.status().execution_uncertain
    assert len(app._session.verify()["checkpoint"]["requests"]) == 1
