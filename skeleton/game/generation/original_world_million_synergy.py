"""Compatibility pressure between 16 world disciplines and 10 game forms.

All 160 numeric couplings are explicit balancing hypotheses. They actually
change risks in the reference game under stress and selected progression;
they are not 160 hand-written stories or 160 additional game foundations.
Review, tune and playtest before using them as production difficulty data.
"""
from __future__ import annotations

from dataclasses import dataclass

DOMAIN_PRESSURE = {
    # platform puzzle tactics survival colony racing stealth commerce exploration rhythm
    "geometry":   (2, 3, 1, 1, 2, 3, 2, 0, 3, 1),
    "chronology": (2, 2, 2, 2, 1, 3, 2, 3, 2, 3),
    "ecosphere":  (1, 0, 1, 3, 3, 1, 1, 2, 3, 1),
    "materials":  (3, 2, 2, 3, 3, 3, 1, 3, 1, 2),
    "governance": (0, 1, 3, 1, 3, 0, 2, 3, 2, 1),
    "community":  (1, 1, 2, 2, 3, 1, 2, 2, 2, 2),
    "commerce":   (1, 2, 2, 3, 3, 2, 1, 3, 1, 2),
    "memory":     (2, 3, 2, 1, 1, 2, 3, 2, 3, 3),
    "language":   (2, 3, 2, 1, 2, 1, 3, 2, 2, 3),
    "metaphysics":(2, 3, 3, 2, 2, 2, 3, 1, 3, 3),
    "navigation": (3, 1, 2, 3, 2, 3, 2, 2, 3, 1),
    "discovery":  (1, 3, 1, 2, 2, 1, 2, 1, 3, 2),
    "simulation": (2, 3, 3, 2, 3, 2, 3, 3, 2, 3),
    "craft":      (2, 3, 1, 3, 3, 2, 1, 3, 2, 2),
    "affection":  (1, 1, 2, 3, 2, 1, 2, 2, 3, 3),
    "survival":   (3, 2, 3, 3, 3, 3, 3, 3, 3, 1),
}
FORM_ORDER = (
    "platform", "puzzle", "tactics", "survival", "colony",
    "racing", "stealth", "commerce", "exploration", "rhythm",
)
ARC_PRESSURE_CONSEQUENCE = {
    "chapters": "duty",
    "endless": "hazard",
    "roguelite": "legacy",
    "dynasty": "outstanding",
    "factions": "trust",
    "sandbox": "reserve",
    "mystery": "uncertainty",
    "seasonal": "warmth",
    "rescue": "outstanding",
    "campaign": "hazard",
    "civilization": "civic",
    "branching": "hazard",
}


@dataclass(frozen=True)
class CrossPressure:
    score: int
    triggered: bool
    consequence: str
    amount: int
    explanation: str


def evaluate_pressure(
    domain: str, form: str, arc: str, genre_stress: int, tick: int,
    checkpoint_interval: int,
) -> CrossPressure:
    """No random/seed/art modifier; same state always has the same pressure."""
    if (domain not in DOMAIN_PRESSURE or form not in FORM_ORDER or
            arc not in ARC_PRESSURE_CONSEQUENCE):
        raise ValueError("unknown authored-law intersection")
    if (type(genre_stress) is not int or not 0 <= genre_stress <= 100 or
            type(tick) is not int or tick < 0 or
            type(checkpoint_interval) is not int or checkpoint_interval < 1):
        raise ValueError("invalid bounded pressure inputs")
    base = DOMAIN_PRESSURE[domain][FORM_ORDER.index(form)]
    score = base + genre_stress // 4
    triggered = tick > 0 and tick % checkpoint_interval == 0 and score >= 4
    consequence = ARC_PRESSURE_CONSEQUENCE[arc]
    # Avoid severe, nonlinear cliffs in consumer-grade pilot simulations.
    amount = min(3, max(1, (score - 2) // 3)) if triggered else 0
    return CrossPressure(
        score, triggered, consequence, amount,
        f"Domain {domain} and {form} physical gameplay exert {score} "
        f"pressure under the {arc} continuation. "
        f"At a checkpoint, {consequence} changes by {amount}.",
    )


if len(DOMAIN_PRESSURE) != 16 or set(ARC_PRESSURE_CONSEQUENCE) != {
    "chapters", "endless", "roguelite", "dynasty", "factions", "sandbox",
    "mystery", "seasonal", "rescue", "campaign", "civilization", "branching",
}:
    raise RuntimeError("missing domain × form × progression constraint data")
if any(len(row) != len(FORM_ORDER) or any(
    type(value) is not int or not 0 <= value <= 3 for value in row
) for row in DOMAIN_PRESSURE.values()):
    raise RuntimeError("missing or unsafe cross-domain genre coefficients")
