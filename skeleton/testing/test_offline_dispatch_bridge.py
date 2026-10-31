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
                4096, 1024, token_budget, 4, 0, hold, "os_probe",
            ),
            {
                "measurement": "os_probe",
                "gpu_device_qualified": False,
                "physical_memory_reserved": False,
                "auxiliary_telemetry_incomplete": True,
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
    with pytest.raises(DispatchUncertain, match="pending"):
        recovered.execute_next(token_budget=32)


def test_status_excludes_keys_and_raw_checkpoint(monkeypatch):
    install_probe(monkeypatch)
    app = make()
    status = app.status()
    assert set(status.__dataclass_fields__) == {
        "schema", "generation", "pending_leases",
        "quarantined", "execution_uncertain",
    }
    assert not status.quarantined
