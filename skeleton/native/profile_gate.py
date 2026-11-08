"""Profile gate for native and JVM acceleration.

Acceleration is selected only from a reproducible profile. A missing profile,
a thin sample, an unproven speedup, or an ABI mismatch stays on the scalar
path. A native call that raises is isolated and the scalar path remains the
correctness owner.

This module does not sign work off and does not claim a completion checkbox.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable

# Keep native telemetry representable and bounded before any speedup division.
MAX_EVIDENCE_INTEGER = (1 << 63) - 1


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

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise ProfileGateError("name must be canonical non-empty text")
        if not isinstance(self.protocol, str) or not self.protocol.strip() or self.protocol != self.protocol.strip():
            raise ProfileGateError("protocol must be canonical non-empty text")
        for field_name in ("samples", "baseline_ns", "candidate_ns", "abi_version"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ProfileGateError(f"{field_name} must be a positive integer")
            if value > MAX_EVIDENCE_INTEGER:
                raise ProfileGateError(f"{field_name} exceeds native evidence bounds")

    def speedup(self) -> float:
        ratio = self.baseline_ns / self.candidate_ns
        if not math.isfinite(ratio):
            raise ProfileGateError("profile speedup must be finite")
        return ratio


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
        if not 0 < expected_abi <= MAX_EVIDENCE_INTEGER:
            raise ProfileGateError("expected_abi must be positive and bounded")
        if not isinstance(protocol, str) or not protocol.strip() or protocol != protocol.strip():
            raise ProfileGateError("protocol must be canonical text")
        if (isinstance(min_samples, bool) or not isinstance(min_samples, int)
                or not 8 <= min_samples <= MAX_EVIDENCE_INTEGER):
            raise ProfileGateError("min_samples must be an integer between 8 and native evidence bounds")
        if not isinstance(min_speedup, (int, float)) or isinstance(min_speedup, bool):
            raise ProfileGateError("min_speedup must be numeric")
        try:
            speedup = float(min_speedup)
        except (OverflowError, ValueError) as exc:
            raise ProfileGateError("min_speedup must be finite") from exc
        if not math.isfinite(speedup) or speedup < 1.0:
            raise ProfileGateError("min_speedup must be finite and at least 1")
        self.expected_abi = expected_abi
        self.protocol = protocol
        self.min_samples = min_samples
        self.min_speedup = speedup

    def decide(self, profile: AccelerationProfile | None) -> GateDecision:
        if profile is None:
            return GateDecision("scalar", "profile-missing")
        if not isinstance(profile, AccelerationProfile):
            raise ProfileGateError("profile must be an AccelerationProfile")
        # A frozen dataclass can still be modified by low-level test or native
        # deserialization tricks: revalidate before any privileged dispatch.
        if (not isinstance(profile.name, str) or not profile.name.strip()
                or profile.name != profile.name.strip()
                or not isinstance(profile.protocol, str) or not profile.protocol.strip()
                or profile.protocol != profile.protocol.strip()):
            return GateDecision("scalar", "profile-identity-invalid")
        numeric = (profile.abi_version, profile.samples,
                   profile.baseline_ns, profile.candidate_ns)
        if any(type(value) is not int or not 0 < value <= MAX_EVIDENCE_INTEGER
               for value in numeric):
            return GateDecision("scalar", "profile-numeric-invalid")
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
