from __future__ import annotations

import pytest

from skeleton.native.profile_gate import (
    AccelerationProfile,
    ProfileGate,
    ProfileGateError,
)


def _profile(**overrides: object) -> AccelerationProfile:
    payload = {
        "name": "vector-dot",
        "samples": 64,
        "baseline_ns": 2000,
        "candidate_ns": 1000,
        "abi_version": 3,
        "protocol": "skeleton.vector.v1",
    }
    payload.update(overrides)
    return AccelerationProfile(**payload)  # type: ignore[arg-type]


def test_gate_selects_native_only_when_profile_justifies() -> None:
    gate = ProfileGate(expected_abi=3, protocol="skeleton.vector.v1")
    decision = gate.decide(_profile())
    assert decision.backend == "native"
    assert decision.as_dict()["stored_prose"] == 0
    assert decision.as_dict()["completion_checkbox"] is False


def test_gate_falls_back_on_thin_sample_abi_and_speedup() -> None:
    gate = ProfileGate(expected_abi=3, protocol="skeleton.vector.v1")
    assert gate.decide(None).reason == "profile-missing"
    assert gate.decide(_profile(samples=4)).reason == "sample-thin"
    assert gate.decide(_profile(abi_version=2)).reason == "abi-mismatch"
    assert gate.decide(_profile(protocol="other")).reason == "protocol-mismatch"
    assert gate.decide(_profile(candidate_ns=1900)).reason == "speedup-unproven"


def test_gate_isolates_native_crash_and_keeps_scalar_result() -> None:
    gate = ProfileGate(expected_abi=3, protocol="skeleton.vector.v1")

    def scalar(payload: int) -> int:
        return payload + 1

    def native(payload: int) -> int:
        raise RuntimeError("abi fault")

    value, decision = gate.call(_profile(), 4, scalar=scalar, native=native)
    assert value == 5
    assert decision.isolated is True
    assert decision.backend == "scalar"


def test_gate_rejects_bad_configuration() -> None:
    with pytest.raises(ProfileGateError):
        ProfileGate(expected_abi=0, protocol="skeleton.vector.v1")
    with pytest.raises(ProfileGateError):
        ProfileGate(expected_abi=1, protocol=" ")
