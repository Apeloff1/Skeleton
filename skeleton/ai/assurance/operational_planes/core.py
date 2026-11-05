"""Fail-closed, deterministic resource and governance plane assessments.

The assessor is intentionally pure: no telemetry requests, implicit file reads,
remote providers, environment-dependent clocks, or policy mutations.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


@dataclass(frozen=True)
class Signal:
    name: str
    maximum: Decimal


@dataclass(frozen=True)
class Plane:
    identity: str
    domain: str
    purpose: str
    signals: tuple[Signal, ...]
    max_age_seconds: int = 60

    def __post_init__(self) -> None:
        if not self.identity or not self.domain or not self.purpose:
            raise ValueError("plane identity, domain and purpose are required")
        if not self.signals or len(set(s.name for s in self.signals)) != len(self.signals):
            raise ValueError("plane signals must be present and unique")
        if self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        for signal in self.signals:
            if not signal.name or not signal.maximum.is_finite() or signal.maximum < 0:
                raise ValueError("invalid signal specification")


@dataclass(frozen=True)
class Assessment:
    plane: str
    status: str
    reason: str
    violations: tuple[str, ...]
    examined: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.status == "nominal"


def _finite_nonnegative(value: object) -> Decimal:
    if isinstance(value, (bool, type(None))):
        raise ValueError("boolean and absent observations are not measurements")
    if not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("unsupported telemetry value type")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid numeric observation") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("measurement must be finite and nonnegative")
    return result


def assess(
    plane: Plane,
    measurements: Mapping[str, object],
    *,
    observed_at: int,
    now: int,
) -> Assessment:
    """Return nominal only when every required bound and custody check passes.

    Missing, malformed, stale and future observations are blocked rather than
    silently treated as zero; extra keys never authorize absent required keys.
    """
    names = tuple(s.name for s in plane.signals)
    if not isinstance(measurements, Mapping):
        return Assessment(plane.identity, "blocked", "measurements-not-mapping", names, ())
    if type(now) is not int or type(observed_at) is not int:
        return Assessment(plane.identity, "blocked", "invalid-clock", names, ())
    if observed_at > now:
        return Assessment(plane.identity, "blocked", "future-observation", names, ())
    if now - observed_at > plane.max_age_seconds:
        return Assessment(plane.identity, "blocked", "stale-observation", names, ())
    missing = tuple(name for name in names if name not in measurements)
    if missing:
        return Assessment(plane.identity, "blocked", "missing-measurement", missing, ())
    invalid: list[str] = []
    breached: list[str] = []
    examined: list[str] = []
    for signal in plane.signals:
        try:
            actual = _finite_nonnegative(measurements[signal.name])
        except ValueError:
            invalid.append(signal.name)
            continue
        examined.append(signal.name)
        if actual > signal.maximum:
            breached.append(signal.name)
    if invalid:
        return Assessment(plane.identity, "blocked", "invalid-measurement",
                          tuple(invalid), tuple(examined))
    if breached:
        return Assessment(plane.identity, "blocked", "threshold-breach",
                          tuple(breached), tuple(examined))
    return Assessment(plane.identity, "nominal", "all-required-signals-within-bounds",
                      (), tuple(examined))
