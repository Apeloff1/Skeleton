"""Canonical live fair-stream budget regressions; simulated probes, no device claim."""
from __future__ import annotations

import pytest

from skeleton.ai.model_runtime import fair_stream_live_budget as module
from skeleton.ai.model_runtime.fair_stream_cli import _command, INPUT_SCHEMA
from skeleton.app.offline_resources import LocalResourceSnapshot
from skeleton.app.offline_io_pressure import IOPressure


def host(*, free_disk=5_000_000_000):
    return LocalResourceSnapshot(
        total_ram_bytes=8_000_000_000,
        available_ram_bytes=4_000_000_000,
        total_disk_bytes=10_000_000_000,
        free_disk_bytes=free_disk,
        cpu_count=8,
        cpu_load_ratio=0.1,
    )


def configure(monkeypatch, *, disk=5_000_000_000, io=None):
    monkeypatch.setattr(module, "probe_local_resources", lambda _: host(free_disk=disk))
    monkeypatch.setattr(module, "probe_cpu_thermal", lambda: ())
    monkeypatch.setattr(module, "probe_io_pressure", lambda: io)
    monkeypatch.setattr(module, "probe_cgroup_events", lambda: None)
    monkeypatch.setattr(module, "probe_cpu_throttle", lambda: None)
    monkeypatch.setattr(module, "probe_swap_counters", lambda: None)
    monkeypatch.setattr(module, "probe_reclaim_counters", lambda: None)


def test_missing_linux_probes_are_explicitly_conservative(monkeypatch):
    configure(monkeypatch)
    budget, evidence = module.LiveStreamBudgetSampler().sample(token_budget=4096)
    assert budget.measurement == "os_probe"
    assert budget.stream_slots <= 1
    assert budget.token_budget == 128
    assert evidence["auxiliary_telemetry_incomplete"] is True
    assert evidence["gpu_device_qualified"] is False
    assert evidence["physical_memory_reserved"] is False


def test_full_disk_reserve_is_hard_hold(monkeypatch):
    configure(monkeypatch, disk=50_000_000)
    budget, evidence = module.LiveStreamBudgetSampler().sample(token_budget=512)
    assert evidence["holds"]["disk_reserve"] is True
    assert budget.effective_slots == 0
    assert budget.effective_tokens == 0


def test_measured_io_stall_never_expands_capacity(monkeypatch):
    configure(monkeypatch, io=IOPressure("host", 30.0, 6.0, 1, 1))
    budget, evidence = module.LiveStreamBudgetSampler().sample(token_budget=1024)
    assert evidence["holds"]["io"] is True
    assert budget.stream_slots <= 1
    assert budget.pressure_ppm >= 850_000


def test_invalid_input_does_not_probe_or_modify_state(monkeypatch):
    configure(monkeypatch)
    sampler = module.LiveStreamBudgetSampler()
    for value in (0, -1, True, 1.5, (1 << 24) + 1):
        with pytest.raises(ValueError):
            sampler.sample(token_budget=value)


def test_cli_live_mode_is_reachable_and_labels_unsupported_devices(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(module, "sys", type("Platform", (), {"platform": "linux"})())
    # The real CLI calls the canonical live sampler, not an operator envelope.
    raw = {
        "schema": INPUT_SCHEMA, "requests": [{
            "request_id": "job", "tenant_id": "owner", "phase": "prefill",
            "remaining_tokens": 12, "bytes_per_token": 4, "priority": 0,
        }],
        "checkpoint": None, "acknowledgments": [], "cancellations": [],
        "envelope": None, "token_budget": 64,
    }
    receipt = _command(raw, live=True, storage_path=".")
    assert receipt["measurement"] == "os_probe"
    assert receipt["live_evidence"]["gpu_device_qualified"] is False
    assert receipt["live_evidence"]["physical_memory_reserved"] is False
    assert receipt["budget"]["stream_slots"] <= 1
    assert len(receipt["plan"]["leases"]) <= 1


def test_unknown_ram_probe_fails_closed(monkeypatch):
    def unavailable(_):
        raise OSError("host probe unavailable")
    monkeypatch.setattr(module, "probe_local_resources", unavailable)
    with pytest.raises(OSError):
        module.LiveStreamBudgetSampler().sample(token_budget=10)
