"""Synthetic monotonic CPU capture tests, not hardware qualification."""
from __future__ import annotations

import pytest

from skeleton.ai.model_runtime.tail_live_capture import LiveTailCapture
from skeleton.ai.model_runtime.tail_latency_profile import ProfileIdentity
from skeleton.app.offline_resources import LocalResourceSnapshot


def identity(evidence="simulated"):
    return ProfileIdentity(
        "a" * 64, "b" * 64, "c" * 64, "d" * 64,
        "e" * 40, "native", "simulated-cpu", evidence,
    )


def snapshot(_):
    return LocalResourceSnapshot(
        total_ram_bytes=4096, available_ram_bytes=2048,
        total_disk_bytes=4096, free_disk_bytes=2048,
        cpu_count=2, cpu_load_ratio=0.25,
    )


def capture(ticks=None, *, max_active=64):
    clock = iter(ticks or [10, 20, 40]).__next__
    return LiveTailCapture(
        identity(), storage_path=".", clock=clock,
        resource_probe=snapshot, max_active=max_active,
    )


def test_measured_state_machine_records_only_completed_request():
    owner = capture()
    owner.begin(request_id="a", prompt_tokens=10)
    assert owner.active_count == 1
    owner.first_token("a")
    timing = owner.complete("a", output_tokens=2, prefix_reused_tokens=1)
    assert timing.started_ns == 10
    assert timing.first_token_ns == 20
    assert timing.completed_ns == 40
    assert owner.active_count == 0
    summary = owner.snapshot(
        ttft_slo_ms=10, inter_token_slo_ms=10, e2e_slo_ms=10,
    )
    assert summary["requests"] == 1
    assert summary["qualification"] == "simulated"
    assert summary["resource"]["min_gpu_free_bytes"] is None


def test_duplicate_and_incomplete_requests_fail_closed():
    owner = capture()
    owner.begin(request_id="a", prompt_tokens=10)
    with pytest.raises(ValueError, match="duplicate"):
        owner.begin(request_id="a", prompt_tokens=10)
    with pytest.raises(ValueError, match="first token"):
        owner.complete("a", output_tokens=1)
    owner.first_token("a")
    with pytest.raises(ValueError, match="transition"):
        owner.first_token("a")
    owner.abort("a")
    with pytest.raises(ValueError, match="duplicate"):
        owner.begin(request_id="a", prompt_tokens=10)
    assert owner.active_count == 0


def test_active_capacity_is_bounded():
    owner = capture([1, 2], max_active=1)
    owner.begin(request_id="a", prompt_tokens=1)
    with pytest.raises(ValueError, match="capacity"):
        owner.begin(request_id="b", prompt_tokens=1)
    owner.abort("a")
    owner.begin(request_id="b", prompt_tokens=1)


def test_invalid_timestamps_never_commit_profile():
    owner = capture([20, 10])
    owner.begin(request_id="a", prompt_tokens=1)
    with pytest.raises(ValueError, match="backwards"):
        owner.first_token("a")
    assert owner.active_count == 1


def test_injected_probes_cannot_claim_real_measured_hardware():
    with pytest.raises(ValueError, match="simulated"):
        LiveTailCapture(
            identity("measured"), storage_path=".",
            clock=lambda: 1, resource_probe=snapshot,
        )


def test_invalid_counts_rejected_before_completion():
    owner = capture()
    with pytest.raises(ValueError, match="prompt"):
        owner.begin(request_id="a", prompt_tokens=True)
    owner.begin(request_id="a", prompt_tokens=10)
    owner.first_token("a")
    with pytest.raises(ValueError, match="output"):
        owner.complete("a", output_tokens=0)
    with pytest.raises(ValueError, match="prefix"):
        owner.complete("a", output_tokens=1, prefix_reused_tokens=11)
    assert owner.active_count == 1


def test_control_characters_and_surrogates_never_enter_timing_state():
    owner = capture()
    for name in ("bad\\nrequest", "\\ud800", "x" * 129):
        with pytest.raises(ValueError, match="bounded request ID"):
            owner.begin(request_id=name, prompt_tokens=1)
    assert owner.active_count == 0


def test_finished_identity_window_is_bounded_and_fails_closed(monkeypatch):
    from skeleton.ai.model_runtime import tail_live_capture as module
    monkeypatch.setattr(module, "MAX_FINISHED", 1)
    owner = capture([1, 2])
    owner.begin(request_id="first", prompt_tokens=1)
    owner.abort("first")
    with pytest.raises(ValueError, match="window exhausted"):
        owner.begin(request_id="second", prompt_tokens=1)
    assert owner.active_count == 0
