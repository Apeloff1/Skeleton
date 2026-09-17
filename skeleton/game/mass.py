"""Clipped snowball mass. Prior times 1.1 max. Stamped 10 with no history is illegal."""

from __future__ import annotations

from typing import Any


MASS_CLIP = 1.1
MASS_EPS = 1e-9
MAX_FORGES = 64


class MassError(ValueError):
    """Mass trajectory violation."""


def clip_mass(prior: float, proposed: float) -> float:
    if isinstance(prior, bool) or isinstance(proposed, bool):
        raise MassError("mass must be numeric")
    if not isinstance(prior, (int, float)) or not isinstance(proposed, (int, float)):
        raise MassError("mass must be numeric")
    if prior <= 0 or proposed <= 0:
        raise MassError("mass must be > 0")
    ceiling = prior * MASS_CLIP
    if proposed > ceiling + MASS_EPS:
        return ceiling
    return float(proposed)


def trajectory(start: float, steps: int, growth: float = MASS_CLIP) -> list[float]:
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise MassError("steps must be a positive integer")
    if steps > MAX_FORGES:
        raise MassError("too many forges")
    if growth > MASS_CLIP + MASS_EPS:
        raise MassError("growth exceeds clip")
    values = [float(start)]
    current = float(start)
    for _ in range(steps):
        current = clip_mass(current, current * growth)
        values.append(current)
    if values[-1] / values[0] > (MASS_CLIP ** steps) + 1e-6:
        raise MassError("trajectory exceeded clip envelope")
    return values


def observe_mass(*, g: float, g0: float, citation: str) -> dict[str, Any]:
    if not citation.strip():
        raise MassError("mass observe requires citation")
    if g == 10.0 and abs(g - g0) < MASS_EPS:
        raise MassError("stamped G=10 without trajectory is forbidden")
    delta = clip_mass(g0, g) - g0 if g >= g0 else 0.0
    return {
        "G": clip_mass(g0, g) if g >= g0 else g0,
        "G0": g0,
        "G_delta": delta,
        "mass_hint": clip_mass(g0, g) if g >= g0 else g0,
        "law": "prior_times_1_1",
        "citation": citation.strip(),
        "stored_prose": 0,
    }
