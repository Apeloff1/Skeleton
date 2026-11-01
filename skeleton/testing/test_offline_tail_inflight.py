"""Application integration of conservative in-flight pressure and tail timing."""
from __future__ import annotations

import pytest

from skeleton.ai.model_runtime.tail_inflight_guard import (
    InFlightCPUResourceGuard, InFlightPressureDenied,
    InFlightPressurePolicy,
)
from skeleton.ai.model_runtime.tail_latency_profile import ProfileIdentity
from skeleton.ai.model_runtime.tail_live_capture import LiveTailCapture
from skeleton.app.offline_cpu_thermal import CPUThermalSensor
from skeleton.app.offline_resources import LocalResourceSnapshot
from skeleton.app.offline_tail_inflight import (
    InFlightLifecycleQuarantined, OfflineTailInFlightSession,
)


def snapshot(_):
    return LocalResourceSnapshot(
        total_ram_bytes=8 << 30, available_ram_bytes=4 << 30,
        total_disk_bytes=100 << 30, free_disk_bytes=50 << 30,
        cpu_count=8, cpu_load_ratio=0.2,
    )


def thermal():
    return (CPUThermalSensor("zone0", "cpu", 40.0, 90.0),)


def controller(*, ticks=(10, 20, 40), capture_probe=snapshot,
               guard_clock=None, quantum_duration_ns=5_000_000_000):
    policy = InFlightPressurePolicy(
        min_ram_bytes=1 << 20, min_disk_bytes=1 << 20,
        max_cpu_load_ppm=900_000, max_memory_pressure_ppm=900_000,
        max_generated_tokens=256, max_quantum_tokens=64,
        max_quantum_duration_ns=quantum_duration_ns,
    )
    guard = InFlightCPUResourceGuard(
        policy, storage_path=".", simulated=True,
        resource_probe=snapshot, thermal_probe=thermal,
        clock=guard_clock,
    )
    identity = ProfileIdentity(
        "a" * 64, "b" * 64, "c" * 64, "d" * 64,
        "e" * 40, "native", "simulated-cpu", "simulated",
    )
    capture = LiveTailCapture(
        identity, storage_path=".",
        clock=iter(ticks).__next__, resource_probe=capture_probe,
    )
    return OfflineTailInFlightSession(guard, capture)


def test_simulated_app_lifecycle_records_tail_without_production_admission():
    app = controller()
    start = app.begin(request_id="a", prompt_tokens=16)
    assert start.state == "running"
    assert start.continue_execution is False
    assert start.gpu_device_qualified is False
    app.first_token()
    step = app.checkpoint(generated_tokens=8)
    assert step.generated_tokens == 8
    done, timing = app.complete(output_tokens=8)
    assert done.state == "completed"
    assert done.continue_execution is False
    assert timing.request_id == "a"
    with pytest.raises(InFlightPressureDenied):
        app.begin(request_id="b", prompt_tokens=1)


def test_duplicate_begin_does_not_reuse_controller():
    app = controller()
    app.begin(request_id="a", prompt_tokens=2)
    with pytest.raises(InFlightPressureDenied, match="one in-flight"):
        app.begin(request_id="a", prompt_tokens=2)


def test_capture_failure_quarantines_after_guard_started():
    app = controller()
    with pytest.raises(InFlightLifecycleQuarantined, match="capture failed"):
        app.begin(request_id="bad\nrequest", prompt_tokens=1)
    assert app.status().telemetry_quarantined
    with pytest.raises(InFlightLifecycleQuarantined):
        app.begin(request_id="other", prompt_tokens=1)


def test_first_token_failure_quarantines():
    app = controller(ticks=(20, 10))
    app.begin(request_id="a", prompt_tokens=1)
    with pytest.raises(InFlightLifecycleQuarantined, match="first-token"):
        app.first_token()
    assert app.status().telemetry_quarantined


def test_late_capture_failure_does_not_report_success():
    def broken_probe(path):
        broken_probe.calls += 1
        if broken_probe.calls > 1:
            raise OSError("telemetry failed")
        return snapshot(path)

    broken_probe.calls = 0
    app = controller(capture_probe=broken_probe)
    app.begin(request_id="a", prompt_tokens=1)
    app.first_token()
    app.checkpoint(generated_tokens=1)
    with pytest.raises(InFlightLifecycleQuarantined, match="completion"):
        app.complete(output_tokens=1)
    assert app.status().telemetry_quarantined
    assert not app.status().continue_execution


def test_abort_is_terminal():
    app = controller()
    app.begin(request_id="a", prompt_tokens=1)
    assert app.abort().state == "aborted"
    with pytest.raises(InFlightPressureDenied):
        app.complete(output_tokens=1)


def test_no_first_token_without_begin():
    app = controller()
    with pytest.raises(InFlightPressureDenied):
        app.first_token()
    with pytest.raises(InFlightPressureDenied):
        app.checkpoint(generated_tokens=1)


def test_app_exposes_bounded_quantum_without_simulated_execution_authority():
    app = controller()
    assert app.begin(request_id="a", prompt_tokens=8).authorized_quantum_tokens == 0
    d = app.admit_quantum(requested_tokens=16)
    assert d.authorized_quantum_tokens == 16
    assert d.continue_execution is False
    assert d.gpu_device_qualified is False
    with pytest.raises(InFlightPressureDenied, match="outstanding"):
        app.complete(output_tokens=0)
    app.first_token()
    app.checkpoint(generated_tokens=8)
    done, timing = app.complete(output_tokens=8)
    assert done.state == "completed"
    assert timing.output_tokens == 8


def test_app_token_mismatch_quarantines_instead_of_publishing_false_tail():
    app = controller()
    app.begin(request_id="a", prompt_tokens=8)
    app.first_token()
    app.checkpoint(generated_tokens=5)
    with pytest.raises(InFlightLifecycleQuarantined, match="token accounting mismatch"):
        app.complete(output_tokens=6)
    assert app.status().telemetry_quarantined
    assert app.status().state == "aborted"
    with pytest.raises(InFlightLifecycleQuarantined):
        app.complete(output_tokens=5)


def test_app_quarantines_on_expired_cpu_quantum_without_tail_completion():
    app = controller(
        guard_clock=iter((100, 200)).__next__,
        quantum_duration_ns=50,
    )
    app.begin(request_id="q", prompt_tokens=3)
    app.admit_quantum(requested_tokens=3)
    with pytest.raises(InFlightLifecycleQuarantined, match="journal reconciliation"):
        app.checkpoint(generated_tokens=3)
    status = app.status()
    assert status.state == "aborted"
    assert status.telemetry_quarantined
    assert not status.continue_execution
    with pytest.raises(InFlightLifecycleQuarantined):
        app.complete(output_tokens=3)


def test_app_first_token_does_not_escape_expired_quantum():
    app = controller(
        guard_clock=iter((100, 200)).__next__,
        quantum_duration_ns=50,
    )
    app.begin(request_id="q", prompt_tokens=3)
    app.admit_quantum(requested_tokens=3)
    with pytest.raises(InFlightLifecycleQuarantined, match="journal reconciliation"):
        app.first_token()
    assert app.status().telemetry_quarantined
    assert app.status().state == "aborted"


def test_unexpected_guard_status_exception_quarantines_app(monkeypatch):
    app = controller()
    app.begin(request_id="unexpected", prompt_tokens=2)
    def broken_status(self):
        raise RuntimeError("unexpected backend status failure")
    with monkeypatch.context() as scoped:
        scoped.setattr(InFlightCPUResourceGuard, "status", broken_status)
        with pytest.raises(InFlightLifecycleQuarantined, match="unexpected CPU guard"):
            app.status()
    after = app.status()
    assert after.telemetry_quarantined
    assert not after.continue_execution
    assert after.state == "aborted"


def test_unexpected_guard_start_exception_never_begins_tail_capture(monkeypatch):
    app = controller()
    def broken_start(self):
        raise RuntimeError("unexpected guard start failure")
    with monkeypatch.context() as scoped:
        scoped.setattr(InFlightCPUResourceGuard, "start", broken_start)
        with pytest.raises(InFlightLifecycleQuarantined, match="unexpected CPU guard"):
            app.begin(request_id="unexpected", prompt_tokens=2)
    assert app.status().telemetry_quarantined
    assert app.status().request_id is None
    with pytest.raises(InFlightLifecycleQuarantined):
        app.begin(request_id="retry", prompt_tokens=2)


def test_app_quarantines_when_unknown_thermal_hold_exceeds_deadline():
    from dataclasses import replace
    app = controller(guard_clock=iter((100, 201)).__next__)
    app._guard.policy = replace(app._guard.policy, max_hold_duration_ns=50)
    app._guard._resource_probe = lambda _: replace(
        snapshot("."), available_ram_bytes=1,
    )
    start = app.begin(request_id="held", prompt_tokens=1)
    assert start.state == "hold"
    assert not start.continue_execution
    with pytest.raises(InFlightLifecycleQuarantined, match="journal reconciliation"):
        app.status()
    after = app.status()
    assert after.state == "aborted"
    assert after.telemetry_quarantined
    assert not after.continue_execution
    with pytest.raises(InFlightLifecycleQuarantined):
        app.resume()


def test_failed_first_token_revokes_cpu_lease_and_cleans_capture():
    app = controller(ticks=(20, 10))
    app.begin(request_id="first-token-failed", prompt_tokens=1)
    assert app._capture.active_count == 1
    with pytest.raises(InFlightLifecycleQuarantined, match="lease revoked"):
        app.first_token()
    assert app._guard.status().state == "aborted"
    assert app._capture.active_count == 0
    assert app.status().telemetry_quarantined
    with pytest.raises(InFlightLifecycleQuarantined):
        app.admit_quantum(requested_tokens=1)


def test_capture_abort_failure_cannot_leave_cpu_guard_running(monkeypatch):
    app = controller()
    app.begin(request_id="abort-capture-failed", prompt_tokens=1)

    def broken_capture_abort(self, request_id):
        raise OSError("injected telemetry cleanup failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(LiveTailCapture, "abort", broken_capture_abort)
        with pytest.raises(InFlightLifecycleQuarantined, match="abort telemetry"):
            app.abort()
    assert app._guard.status().state == "aborted"
    assert app.status().telemetry_quarantined
    assert not app.status().continue_execution
    with pytest.raises(InFlightLifecycleQuarantined):
        app.admit_quantum(requested_tokens=1)


def test_guard_abort_failure_quarantines_and_cleans_capture(monkeypatch):
    app = controller()
    app.begin(request_id="abort-guard-failed", prompt_tokens=1)

    def broken_guard_abort(self):
        raise RuntimeError("injected CPU cancellation failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(InFlightCPUResourceGuard, "abort", broken_guard_abort)
        with pytest.raises(InFlightLifecycleQuarantined, match="abort guard"):
            app.abort()
    assert app._capture.active_count == 0
    assert app.status().telemetry_quarantined
    assert not app.status().continue_execution
    with pytest.raises(InFlightLifecycleQuarantined):
        app.complete(output_tokens=1)
