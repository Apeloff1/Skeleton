"""Transportability stress tests across increasing environment shift."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class TransportStressPoint:
    point_id: str
    probe_digest: str
    shift_severity: float
    source_effect: float
    target_effect: float

    def __post_init__(self) -> None:
        if not self.point_id:
            raise ReverseEngineeringError("transport stress point requires identity")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be sha256 hex")
        for value, name in (
            (self.shift_severity, "shift_severity"),
            (self.source_effect, "source_effect"),
            (self.target_effect, "target_effect"),
        ):
            if not isfinite(value):
                raise ReverseEngineeringError(f"{name} must be finite")
        if self.shift_severity < 0.0:
            raise ReverseEngineeringError("shift_severity must be non-negative")

    @property
    def gap(self) -> float:
        return abs(self.target_effect - self.source_effect)


@dataclass(frozen=True)
class TransportStressReport:
    point_count: int
    min_shift_severity: float
    max_shift_severity: float
    baseline_gap: float
    terminal_gap: float
    gap_growth: float
    first_gap_above_tolerance: float | None
    sign_flip_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "point_count": self.point_count,
            "min_shift_severity": self.min_shift_severity,
            "max_shift_severity": self.max_shift_severity,
            "baseline_gap": self.baseline_gap,
            "terminal_gap": self.terminal_gap,
            "gap_growth": self.gap_growth,
            "first_gap_above_tolerance": self.first_gap_above_tolerance,
            "sign_flip_count": self.sign_flip_count,
            "digest": self.digest,
        }


def analyze_transport_stress(
    points: Sequence[TransportStressPoint],
    *,
    gap_tolerance: float = 0.2,
) -> TransportStressReport:
    if len(points) < 2:
        raise ReverseEngineeringError("transport stress requires at least two points")
    if not isfinite(gap_tolerance) or gap_tolerance < 0.0:
        raise ReverseEngineeringError("gap_tolerance must be finite and non-negative")
    digests = {item.probe_digest for item in points}
    if len(digests) != 1:
        raise ReverseEngineeringError("transport stress points must share probe_digest")
    ordered = sorted(points, key=lambda item: (item.shift_severity, item.point_id))
    severities = [item.shift_severity for item in ordered]
    if len(severities) != len(set(severities)):
        raise ReverseEngineeringError("shift severities must be unique")
    above = [item.shift_severity for item in ordered if item.gap > gap_tolerance]
    sign_flips = sum(
        (item.source_effect > 0.0 > item.target_effect)
        or (item.source_effect < 0.0 < item.target_effect)
        for item in ordered
    )
    payload = {
        "probe_digest": next(iter(digests)),
        "gap_tolerance": gap_tolerance,
        "points": [
            {
                "point_id": item.point_id,
                "shift_severity": item.shift_severity,
                "source_effect": item.source_effect,
                "target_effect": item.target_effect,
            }
            for item in ordered
        ],
    }
    return TransportStressReport(
        point_count=len(ordered),
        min_shift_severity=ordered[0].shift_severity,
        max_shift_severity=ordered[-1].shift_severity,
        baseline_gap=ordered[0].gap,
        terminal_gap=ordered[-1].gap,
        gap_growth=ordered[-1].gap - ordered[0].gap,
        first_gap_above_tolerance=min(above) if above else None,
        sign_flip_count=sign_flips,
        digest=stable_digest(payload),
    )
