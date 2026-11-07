"""Controls flight probe evaluator (pure half of ``qa-flight.mjs``).

The browser half steers left then right and records yaw before/after each
input. A pass needs a clear positive yaw delta for +steer, a clear negative one
for -steer, and zero console/page errors. Deltas are angle-wrapped to (-pi, pi].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

DEFAULT_MIN_DELTA = 0.05


def wrap_angle(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


@dataclass(frozen=True)
class FlightProbe:
    ok: bool
    y0: float = 0.0
    y_a: float = 0.0
    y1: float = 0.0
    y_d: float = 0.0
    speed: float = 0.0
    reason: str = ""

    @property
    def d_a(self) -> float:
        return wrap_angle(self.y_a - self.y0)

    @property
    def d_d(self) -> float:
        return wrap_angle(self.y_d - self.y1)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "FlightProbe":
        d = d or {}
        if not d.get("ok"):
            return cls(ok=False, reason=str(d.get("reason", "no probe")))
        y1 = d.get("y1", d.get("yA", 0.0))
        return cls(
            ok=True,
            y0=float(d.get("y0", 0.0)),
            y_a=float(d.get("yA", 0.0)),
            y1=float(y1),
            y_d=float(d.get("yD", 0.0)),
            speed=float(d.get("speed", 0.0)),
        )


@dataclass
class FlightVerdict:
    passed: bool
    d_a: float
    d_d: float
    failures: list[str] = field(default_factory=list)


def evaluate_flight(
    probe: FlightProbe,
    errors: Sequence[str] = (),
    *,
    min_delta: float = DEFAULT_MIN_DELTA,
    min_speed: float = 0.0,
) -> FlightVerdict:
    failures: list[str] = []
    if not probe.ok:
        return FlightVerdict(
            False, 0.0, 0.0, [f"probe unavailable: {probe.reason or 'no probe'}"]
        )
    if probe.d_a <= min_delta:
        failures.append(f"+steer yaw delta {probe.d_a:.3f} <= {min_delta}")
    if probe.d_d >= -min_delta:
        failures.append(f"-steer yaw delta {probe.d_d:.3f} >= {-min_delta}")
    if probe.speed < min_speed:
        failures.append(f"speed {probe.speed:.2f} below {min_speed}")
    if errors:
        failures.append(f"{len(errors)} console/page error(s)")
    return FlightVerdict(not failures, probe.d_a, probe.d_d, failures)
