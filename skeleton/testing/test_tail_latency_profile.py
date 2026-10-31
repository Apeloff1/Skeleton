"""Deterministic source-backed tests for local inference tail profiles.

The fixture timings are synthetic and explicitly marked simulated unless a
test is verifying the semantics of an asserted measured input contract.
"""
from __future__ import annotations

import io
import json
import sys
from types import SimpleNamespace

import pytest

from skeleton.ai.model_runtime.execution_telemetry import ExecutionTiming
from skeleton.ai.model_runtime.tail_latency_cli import _command, main
from skeleton.ai.model_runtime.tail_latency_profile import (
    LocalTailProfiler, ProfileIdentity, ResourceObservation,
    compare_tail_profiles,
)


def identity(*, evidence: str = "simulated", device: str = "simulated-cpu") -> ProfileIdentity:
    return ProfileIdentity(
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 40,
        "native-transformer", device, evidence,
    )


def resource(*, thermal: str = "measured_ok", gpu: bool = False) -> ResourceObservation:
    return ResourceObservation(
        ram_available_bytes=1 << 29,
        ram_total_bytes=1 << 30,
        swap_free_bytes=1 << 29,
        swap_total_bytes=1 << 30,
        cpu_load_ppm=100_000,
        thermal=thermal,
        gpu_free_bytes=(1 << 29) if gpu else None,
        gpu_total_bytes=(1 << 30) if gpu else None,
    )


def timing(index: int, *, latency_ms: int | None = None) -> ExecutionTiming:
    latency = index if latency_ms is None else latency_ms
    return ExecutionTiming(
        request_id="req-" + str(index),
        started_ns=0,
        first_token_ns=latency * 1_000_000,
        completed_ns=(latency + 10) * 1_000_000,
        output_tokens=10,
        prompt_tokens=20,
        prefix_reused_tokens=5,
    )


def profile(*, extra_ms: int = 0, evidence: str = "measured") -> LocalTailProfiler:
    result = LocalTailProfiler(identity(evidence=evidence))
    for index in range(1, 101):
        result.record(timing(index, latency_ms=index + extra_ms), resource())
    return result


def summary(profiler: LocalTailProfiler) -> dict[str, object]:
    return profiler.summary(
        ttft_slo_ms=100, inter_token_slo_ms=5, e2e_slo_ms=120,
    )


def test_exact_nearest_rank_percentiles() -> None:
    report = summary(profile())
    assert report["tail"]["ttft_ms"] == {
        "p50": 50, "p95": 95, "p99": 99, "max": 100,
    }
    assert report["tail"]["e2e_ms"]["p95"] == 105
    assert report["tail"]["e2e_ms"]["p99"] == 109
    assert report["requests"] == 100
    assert report["qualification"] == "measured_tail_profile"
    assert report["serial_throughput_only"] is True
    assert report["serial_tokens_per_second_milli"] > 0


def test_goodput_is_canonical_serving_telemetry() -> None:
    report = summary(profile())
    assert report["slo"]["requests"] == 100
    assert report["slo"]["slo_compliant_requests"] == 100
    assert report["slo"]["goodput_pct"] == 100.0
    assert report["slo"]["prefix_reused_tokens"] == 500


def test_profile_is_deterministic_across_input_order() -> None:
    first = LocalTailProfiler(identity())
    second = LocalTailProfiler(identity())
    for index in (1, 3, 2):
        first.record(timing(index), resource())
    for index in (3, 2, 1):
        second.record(timing(index), resource())
    assert summary(first) == summary(second)
    assert first.checkpoint() == second.checkpoint()


def test_insufficient_samples_never_claim_tail_qualification() -> None:
    profiler = LocalTailProfiler(identity(evidence="measured"))
    profiler.record(timing(1), resource())
    report = summary(profiler)
    assert report["qualification"] == "insufficient_samples"
    assert not report["minimum_tail_sample_count_met"]


def test_simulated_samples_cannot_certify_real_hardware() -> None:
    report = summary(profile(evidence="simulated"))
    assert report["qualification"] == "simulated"
    with pytest.raises(ValueError, match="simulated"):
        compare_tail_profiles(report, report)


def test_thermal_unknown_and_hold_block_qualification() -> None:
    for thermal, expected in (
        ("unavailable", "thermal_unknown"),
        ("measured_hold", "thermal_hold"),
    ):
        profiler = LocalTailProfiler(identity(evidence="measured"))
        for index in range(1, 101):
            profiler.record(timing(index), resource(thermal=thermal))
        assert summary(profiler)["qualification"] == expected


def test_identical_identity_measured_tail_regression() -> None:
    baseline = summary(profile(extra_ms=0))
    candidate = summary(profile(extra_ms=100))
    decision = compare_tail_profiles(
        baseline, candidate, allowed_regression_ppm=50_000,
    )
    assert decision["status"] == "regression"
    assert "ttft_ms.p95" in decision["violations"]
    assert "e2e_ms.p99" in decision["violations"]


def test_equal_profiles_pass_tail_regression() -> None:
    report = summary(profile())
    decision = compare_tail_profiles(report, report)
    assert decision["status"] == "no_regression"
    assert decision["violations"] == []


def test_mismatched_device_or_model_is_not_comparable() -> None:
    baseline = summary(profile())
    other = LocalTailProfiler(identity(evidence="measured", device="other"))
    for index in range(1, 101):
        other.record(timing(index), resource())
    with pytest.raises(ValueError, match="different"):
        compare_tail_profiles(baseline, summary(other))


def test_checkpoint_restore_exact_and_no_double_record() -> None:
    profiler = LocalTailProfiler(identity())
    profiler.record(timing(1), resource())
    restored = LocalTailProfiler.restore(profiler.checkpoint())
    assert restored.checkpoint() == profiler.checkpoint()
    with pytest.raises(ValueError, match="duplicate"):
        restored.record(timing(1), resource())
    restored.record(timing(2), resource())
    assert summary(restored)["requests"] == 2


def test_checkpoint_tampering_is_detected() -> None:
    profiler = LocalTailProfiler(identity())
    profiler.record(timing(1), resource())
    state = profiler.checkpoint()
    state["records"][0]["output_tokens"] = 100
    with pytest.raises(ValueError, match="integrity"):
        LocalTailProfiler.restore(state)


def test_record_capacity_and_invalid_identity_fail_closed() -> None:
    profiler = LocalTailProfiler(identity(), max_records=1)
    profiler.record(timing(1), resource())
    with pytest.raises(ValueError, match="full"):
        profiler.record(timing(2), resource())
    with pytest.raises(ValueError):
        identity(device="bad\nid")
    with pytest.raises(ValueError):
        ProfileIdentity("x", "b" * 64, "c" * 64, "d" * 64, "e" * 40, "b", "d")


@pytest.mark.parametrize("kwargs", [
    {"ram_available_bytes": 2 << 30},
    {"cpu_load_ppm": True},
    {"thermal": "unknown-ok"},
    {"gpu_free_bytes": 10, "gpu_total_bytes": None},
    {"gpu_free_bytes": 100, "gpu_total_bytes": 50},
])
def test_resource_observation_rejects_false_capacity(kwargs: dict[str, object]) -> None:
    fields = resource().to_dict()
    fields.update(kwargs)
    with pytest.raises(ValueError):
        ResourceObservation(**fields)


def _payload() -> dict[str, object]:
    return {
        "schema": "skeleton.ai.tail-profile-command.v1",
        "identity": identity().to_dict(),
        "records": [{
            "timing": {
                "request_id": "r1", "started_ns": 0,
                "first_token_ns": 1_000_000, "completed_ns": 11_000_000,
                "output_tokens": 10, "prompt_tokens": 20,
                "prefix_reused_tokens": 5,
            },
            "resource": resource().to_dict(),
        }],
        "checkpoint": None,
        "slo": {
            "ttft_slo_ms": 100, "inter_token_slo_ms": 5, "e2e_slo_ms": 120,
        },
        "baseline": None,
        "allowed_regression_ppm": None,
    }


def test_cli_profile_roundtrip_and_source_binding() -> None:
    first = _command(_payload())
    assert first["summary"]["requests"] == 1
    assert first["device_qualified"] is False
    assert first["model_quality_qualified"] is False
    followup = _payload()
    followup["records"] = []
    followup["checkpoint"] = first["checkpoint"]
    assert _command(followup)["summary"] == first["summary"]


def test_cli_rejects_identity_switch_on_restore() -> None:
    first = _command(_payload())
    followup = _payload()
    followup["checkpoint"] = first["checkpoint"]
    followup["records"] = []
    followup["identity"]["device"] = "other"
    with pytest.raises(ValueError, match="identity mismatch"):
        _command(followup)


def test_cli_enforces_input_budget(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"x" * 524289)))
    assert main([]) == 2
    assert "byte budget" in capsys.readouterr().err


def test_cli_prints_redacted_receipt(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys, "stdin",
        SimpleNamespace(buffer=io.BytesIO(json.dumps(_payload()).encode("utf-8"))),
    )
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["summary"]["requests"] == 1
    assert "prompt_text" not in json.dumps(output)
    assert output["device_qualified"] is False
