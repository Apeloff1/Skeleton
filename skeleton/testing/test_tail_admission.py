"""Deterministic CPU admission tests; profiles are simulated, not device proof."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import pytest

from skeleton.ai.model_runtime.tail_admission import (
    TailAdmissionGovernor, TailAdmissionPolicy,
)
from skeleton.ai.model_runtime.tail_latency_profile import PROFILE_SCHEMA


def policy():
    return TailAdmissionPolicy(8, 1024, 100, 500, 3, 25)


def profile(n: int, *, measured: bool = True, ttft: int = 40, e2e: int = 200,
            thermal_unknown: int = 0, ram: int = 16384):
    body = {
        "schema": PROFILE_SCHEMA,
        "identity": {"evidence": "measured" if measured else "simulated"},
        "requests": 100, "minimum_tail_sample_count_met": True,
        "qualification": "measured_tail_profile" if measured else "simulated",
        "resource": {
            "thermal_unavailable_samples": thermal_unknown,
            "thermal_hold_samples": 0, "min_ram_available_bytes": ram,
        },
        "tail": {
            "ttft_ms": {"p99": ttft}, "e2e_ms": {"p99": e2e},
        },
        "observation_number": n,
    }
    return {**body, "digest": hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()}


def test_three_good_windows_required_to_admit_first_slot():
    governor = TailAdmissionGovernor(policy())
    for n in (1, 2):
        receipt = governor.observe(
            profile(n), expected_generation=n - 1,
            current_ram_available_bytes=16384,
        )
        assert receipt["admitted_slots"] == 0
    receipt = governor.observe(
        profile(3), expected_generation=2,
        current_ram_available_bytes=16384,
    )
    assert receipt["admitted_slots"] == 1
    assert receipt["device_qualified"] is False


def test_p99_regression_halves_slots_and_resets_hysteresis():
    governor = TailAdmissionGovernor(policy(), slots=6)
    receipt = governor.observe(
        profile(1, ttft=120), expected_generation=0,
        current_ram_available_bytes=16384,
    )
    assert receipt["admitted_slots"] == 3
    assert receipt["reason"] == "p99_backpressure"


def test_unqualified_thermal_unknown_and_low_ram_hold():
    for candidate, ram in (
        (profile(1, measured=False), 16384),
        (profile(1, thermal_unknown=1), 16384),
        (profile(1), 0),
    ):
        governor = TailAdmissionGovernor(policy(), slots=5)
        result = governor.observe(
            candidate, expected_generation=0,
            current_ram_available_bytes=ram,
        )
        assert result["admitted_slots"] == 0


def test_replay_and_tamper_do_not_mutate_checkpoint():
    governor = TailAdmissionGovernor(policy(), slots=2)
    original = profile(1)
    governor.observe(original, expected_generation=0, current_ram_available_bytes=16384)
    state = governor.checkpoint()
    with pytest.raises(ValueError, match="replayed"):
        governor.observe(original, expected_generation=1, current_ram_available_bytes=16384)
    forged = deepcopy(profile(2))
    forged["tail"]["e2e_ms"]["p99"] = 999999
    with pytest.raises(ValueError, match="integrity"):
        governor.observe(forged, expected_generation=1, current_ram_available_bytes=16384)
    assert governor.checkpoint() == state


def test_restore_roundtrip_and_corrupt_checkpoint():
    governor = TailAdmissionGovernor(policy(), slots=2)
    governor.observe(profile(1), expected_generation=0, current_ram_available_bytes=16384)
    state = governor.checkpoint()
    assert TailAdmissionGovernor.restore(state).checkpoint() == state
    forged = deepcopy(state)
    forged["slots"] = 8
    with pytest.raises(ValueError, match="integrity"):
        TailAdmissionGovernor.restore(forged)


def test_invalid_policy_rejects_boolean_and_zero_limits():
    with pytest.raises(ValueError):
        TailAdmissionPolicy(True, 1024, 100, 500)
    with pytest.raises(ValueError):
        TailAdmissionPolicy(8, 0, 100, 500)
