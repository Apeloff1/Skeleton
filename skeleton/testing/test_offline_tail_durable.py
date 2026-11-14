"""Simulated app integration for durable tail profile publication."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.ai.model_runtime.execution_telemetry import ExecutionTiming
from skeleton.ai.model_runtime.tail_latency_profile import (
    ProfileIdentity, ResourceObservation,
)
from skeleton.ai.model_runtime.tail_profile_custody import (
    DurableTailProfileStore, TailCustodyQuarantined,
)
from skeleton.app.offline_tail_durable import OfflineDurableTailRecorder
from skeleton.app.offline_tail_profile_adapter import LocalTailObservationCapture


class Anchor:
    """Test-only CAS; not an independent durable hardware or key boundary."""

    def __init__(self):
        self.value = None
        self.fail = False

    def initialize(self, *, generation, digest):
        if self.value is not None:
            raise ValueError("already initialized")
        self.value = generation, digest

    def read(self):
        if self.value is None:
            raise ValueError("missing anchor")
        return self.value

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.value != (expected_generation, expected_digest) or self.fail:
            raise ValueError("anchor CAS refused")
        self.value = generation, digest


def identity():
    return ProfileIdentity(
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 40,
        "cpu", "simulated-cpu", "simulated",
    )


def timing(index):
    return ExecutionTiming(
        request_id=f"r-{index}", started_ns=0,
        first_token_ns=index * 1_000_000,
        completed_ns=(index + 10) * 1_000_000,
        output_tokens=10, prompt_tokens=20, prefix_reused_tokens=5,
    )


def resource():
    return ResourceObservation(
        ram_available_bytes=1000, ram_total_bytes=2000,
        swap_free_bytes=100, swap_total_bytes=200,
        cpu_load_ppm=100000, thermal="unavailable",
    )


def capture_simulated(self, timing):
    self.profiler.record(timing, resource())
    return None


def store(connection, anchor):
    return DurableTailProfileStore(
        connection, anchor, key=b"k" * 32, identity=identity(),
    )


def test_app_persists_before_reporting_and_restores(monkeypatch, tmp_path):
    monkeypatch.setattr(LocalTailObservationCapture, "capture", capture_simulated)
    path = tmp_path / "tail.db"
    anchor = Anchor()
    connection = sqlite3.connect(path)
    app = OfflineDurableTailRecorder(store(connection, anchor), bootstrap=True)
    assert app.status().requests == 0
    receipt = app.capture(timing(1))
    assert receipt.requests == 1 and receipt.generation == 1
    assert receipt.device_qualified is False
    connection.close()
    restored = OfflineDurableTailRecorder(
        store(sqlite3.connect(path), anchor), bootstrap=False,
    )
    assert restored.status().requests == 1
    assert restored.capture(timing(2)).generation == 2


def test_app_quarantines_after_external_cas_failure(monkeypatch):
    monkeypatch.setattr(LocalTailObservationCapture, "capture", capture_simulated)
    anchor = Anchor()
    app = OfflineDurableTailRecorder(
        store(sqlite3.connect(":memory:"), anchor), bootstrap=True,
    )
    anchor.fail = True
    with pytest.raises(TailCustodyQuarantined):
        app.capture(timing(1))
    with pytest.raises(TailCustodyQuarantined):
        app.capture(timing(2))
    with pytest.raises(TailCustodyQuarantined):
        app.status()


def test_app_rejects_duplicate_after_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(LocalTailObservationCapture, "capture", capture_simulated)
    path = tmp_path / "tail.db"
    anchor = Anchor()
    connection = sqlite3.connect(path)
    app = OfflineDurableTailRecorder(store(connection, anchor), bootstrap=True)
    app.capture(timing(1))
    connection.close()
    recovered = OfflineDurableTailRecorder(
        store(sqlite3.connect(path), anchor), bootstrap=False,
    )
    with pytest.raises(ValueError, match="duplicate"):
        recovered.capture(timing(1))
    with pytest.raises(TailCustodyQuarantined):
        recovered.status()


def test_status_rejects_anchor_change_between_reads(monkeypatch):
    monkeypatch.setattr(LocalTailObservationCapture, "capture", capture_simulated)
    anchor = Anchor()
    custody = store(sqlite3.connect(":memory:"), anchor)
    app = OfflineDurableTailRecorder(custody, bootstrap=True)
    original = custody.load
    def race():
        profile = original()
        anchor.value = (123, "f" * 64)
        return profile
    monkeypatch.setattr(custody, "load", race)
    with pytest.raises(TailCustodyQuarantined, match="status"):
        app.status()
    assert custody.quarantined
