"""Profile gate for native and JVM acceleration.

Acceleration is selected only from a reproducible profile. A missing profile,
a thin sample, an unproven speedup, or an ABI mismatch stays on the scalar
path. A native call that raises is isolated and the scalar path remains the
correctness owner.

This module does not sign work off and does not claim a completion checkbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class ProfileGateError(RuntimeError):
    """Profile input cannot be interpreted. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class AccelerationProfile:
    name: str
    samples: int
    baseline_ns: int
    candidate_ns: int
    abi_version: int
    protocol: str

    def speedup(self) -> float:
        if self.candidate_ns <= 0:
            raise ProfileGateError("candidate_ns must be positive")
        return self.baseline_ns / self.candidate_ns


@dataclass(frozen=True, slots=True)
class GateDecision:
    backend: str
    reason: str
    isolated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "native_profile_gate",
            "hit": self.backend == "native",
            "law": "profile-gated-acceleration",
            "citation": "VOL-032",
            "backend": self.backend,
            "reason": self.reason,
            "isolated": self.isolated,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }


Scalar = Callable[[Any], Any]
Native = Callable[[Any], Any]


class ProfileGate:
    """Select native only when the profile justifies it."""

    def __init__(
        self,
        *,
        expected_abi: int,
        protocol: str,
        min_samples: int = 32,
        min_speedup: float = 1.10,
    ) -> None:
        if isinstance(expected_abi, bool) or not isinstance(expected_abi, int):
            raise ProfileGateError("expected_abi must be an integer")
        if expected_abi < 1:
            raise ProfileGateError("expected_abi must be positive")
        if not isinstance(protocol, str) or not protocol.strip() or protocol != protocol.strip():
            raise ProfileGateError("protocol must be canonical text")
        if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 8:
            raise ProfileGateError("min_samples must be an integer >= 8")
        if not isinstance(min_speedup, (int, float)) or isinstance(min_speedup, bool):
            raise ProfileGateError("min_speedup must be numeric")
        if float(min_speedup) < 1.0:
            raise ProfileGateError("min_speedup must be at least 1")
        self.expected_abi = expected_abi
        self.protocol = protocol
        self.min_samples = min_samples
        self.min_speedup = float(min_speedup)

    def decide(self, profile: AccelerationProfile | None) -> GateDecision:
        if profile is None:
            return GateDecision("scalar", "profile-missing")
        if not isinstance(profile, AccelerationProfile):
            raise ProfileGateError("profile must be an AccelerationProfile")
        if profile.protocol != self.protocol:
            return GateDecision("scalar", "protocol-mismatch")
        if profile.abi_version != self.expected_abi:
            return GateDecision("scalar", "abi-mismatch")
        if profile.samples < self.min_samples:
            return GateDecision("scalar", "sample-thin")
        if profile.baseline_ns <= 0 or profile.candidate_ns <= 0:
            return GateDecision("scalar", "timing-invalid")
        if profile.speedup() < self.min_speedup:
            return GateDecision("scalar", "speedup-unproven")
        return GateDecision("native", "profile-justified")

    def call(
        self,
        profile: AccelerationProfile | None,
        payload: Any,
        *,
        scalar: Scalar,
        native: Native | None = None,
    ) -> tuple[Any, GateDecision]:
        decision = self.decide(profile)
        if decision.backend != "native" or native is None:
            return scalar(payload), decision
        try:
            return native(payload), decision
        except Exception:
            isolated = GateDecision("scalar", "crash-isolated", isolated=True)
            return scalar(payload), isolated

    def card(self, decision: GateDecision) -> dict[str, Any]:
        return decision.as_dict()
