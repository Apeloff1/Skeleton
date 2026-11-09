"""Deterministic damage model: typed damage, armor/resist mitigation, crit, variance.

Design rules (Combat Design Lead):

* Every number is bounded and validated; bad input fails closed with ``ValueError``.
* Mitigation uses a diminishing-returns curve so armor stacking never reaches
  immunity: ``dr = armor / (armor + ARMOR_K * attacker_level + ARMOR_BASE)``,
  hard-capped at ``MAX_ARMOR_DR``.
* Elemental resistances are flat fractions capped at ``MAX_RESIST``.
* ``TRUE`` damage ignores all mitigation (reserved for enrage / mechanic failure).
* Variance is a narrow, symmetric band so hits feel consistent ("weight"):
  the same attack always lands within ``+/-VARIANCE_BAND`` of its expected value.
* No process randomness: callers pass rolls in ``[0, 1)`` (e.g. from
  :class:`SeededEntropy`), so the same rolls give the same result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Mapping, Tuple

ARMOR_K = 85.0
ARMOR_BASE = 400.0
MAX_ARMOR_DR = 0.75
MAX_RESIST = 0.75
MAX_VULNERABILITY = 1.5
VARIANCE_BAND = 0.05
MAX_BASE_DAMAGE = 1_000_000
MAX_LEVEL = 100
MAX_ARMOR = 100_000
MAX_CRIT_MULT = 4.0


class DamageType(str, Enum):
    PHYSICAL = "physical"
    FIRE = "fire"
    FROST = "frost"
    LIGHTNING = "lightning"
    POISON = "poison"
    SHADOW = "shadow"
    TRUE = "true"


ELEMENTAL_TYPES = frozenset(
    {DamageType.FIRE, DamageType.FROST, DamageType.LIGHTNING, DamageType.POISON, DamageType.SHADOW}
)


@dataclass(frozen=True)
class DamageEvent:
    """One outgoing hit before the defender's mitigation."""

    base: float
    dtype: DamageType = DamageType.PHYSICAL
    attacker_level: int = 1
    crit_chance: float = 0.0
    crit_mult: float = 2.0
    can_crit: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.dtype, DamageType):
            raise ValueError("dtype must be a DamageType")
        if not (0 <= self.base <= MAX_BASE_DAMAGE):
            raise ValueError("base damage out of bounds")
        if not (1 <= self.attacker_level <= MAX_LEVEL):
            raise ValueError("attacker level out of bounds")
        if not (0.0 <= self.crit_chance <= 1.0):
            raise ValueError("crit chance out of bounds")
        if not (1.0 <= self.crit_mult <= MAX_CRIT_MULT):
            raise ValueError("crit multiplier out of bounds")


@dataclass(frozen=True)
class DefenderProfile:
    """Defensive stats of the target."""

    armor: float = 0.0
    resistances: Mapping[DamageType, float] = field(default_factory=dict)
    flat_reduction: float = 0.0
    vulnerability: float = 1.0

    def __post_init__(self) -> None:
        if not (0 <= self.armor <= MAX_ARMOR):
            raise ValueError("armor out of bounds")
        if self.flat_reduction < 0:
            raise ValueError("flat reduction must be >= 0")
        if not (0.5 <= self.vulnerability <= MAX_VULNERABILITY):
            raise ValueError("vulnerability out of bounds")
        for dtype, value in dict(self.resistances).items():
            if dtype not in ELEMENTAL_TYPES:
                raise ValueError(f"resistance not allowed for {dtype}")
            if not (0.0 <= value <= 1.0):
                raise ValueError("resistance out of bounds")


@dataclass(frozen=True)
class DamageResult:
    pre_mitigation: float
    mitigation_fraction: float
    final: int
    crit: bool
    breakdown: Tuple[Tuple[str, float], ...]

    def as_dict(self) -> Dict[str, object]:
        return {
            "pre_mitigation": round(self.pre_mitigation, 4),
            "mitigation_fraction": round(self.mitigation_fraction, 6),
            "final": self.final,
            "crit": self.crit,
            "breakdown": [[k, round(v, 4)] for k, v in self.breakdown],
        }


def armor_damage_reduction(armor: float, attacker_level: int) -> float:
    """Diminishing-returns armor DR; monotone in armor, never above the cap."""

    if armor < 0 or not (1 <= attacker_level <= MAX_LEVEL):
        raise ValueError("bad armor inputs")
    if armor == 0:
        return 0.0
    dr = armor / (armor + ARMOR_K * attacker_level + ARMOR_BASE)
    return min(MAX_ARMOR_DR, dr)


def mitigation_fraction(event: DamageEvent, defender: DefenderProfile) -> float:
    """Fraction of the hit removed by the defender (0 = full damage)."""

    if event.dtype is DamageType.TRUE:
        return 0.0
    if event.dtype is DamageType.PHYSICAL:
        return armor_damage_reduction(defender.armor, event.attacker_level)
    resist = float(dict(defender.resistances).get(event.dtype, 0.0))
    return min(MAX_RESIST, resist)


def _check_roll(roll: float, name: str) -> None:
    if not (0.0 <= roll < 1.0):
        raise ValueError(f"{name} must be in [0, 1)")


def resolve_damage(
    event: DamageEvent,
    defender: DefenderProfile,
    *,
    crit_roll: float,
    variance_roll: float = 0.5,
) -> DamageResult:
    """Resolve one hit deterministically from two rolls in ``[0, 1)``."""

    _check_roll(crit_roll, "crit_roll")
    _check_roll(variance_roll, "variance_roll")
    variance = 1.0 + VARIANCE_BAND * (2.0 * variance_roll - 1.0)
    crit = event.can_crit and crit_roll < event.crit_chance
    crit_factor = event.crit_mult if crit else 1.0
    pre = event.base * variance * crit_factor
    mit = mitigation_fraction(event, defender)
    after_mit = pre * (1.0 - mit)
    if event.dtype is DamageType.TRUE:
        flat = 0.0
        vuln = 1.0
    else:
        flat = float(defender.flat_reduction)
        vuln = defender.vulnerability
    final_value = max(0.0, after_mit - flat) * vuln
    final = int(round(final_value))
    breakdown = (
        ("base", float(event.base)),
        ("variance", variance),
        ("crit_factor", crit_factor),
        ("mitigation", mit),
        ("flat_reduction", flat),
        ("vulnerability", vuln),
    )
    return DamageResult(pre, mit, final, crit, breakdown)


def expected_damage(event: DamageEvent, defender: DefenderProfile) -> float:
    """Analytic mean damage per hit at the variance midpoint.

    Flat reduction is applied per branch (crit / non-crit) to stay exact.
    """

    mit = mitigation_fraction(event, defender)
    flat = 0.0 if event.dtype is DamageType.TRUE else defender.flat_reduction
    vuln = 1.0 if event.dtype is DamageType.TRUE else defender.vulnerability
    p = event.crit_chance if event.can_crit else 0.0

    def branch(mult: float) -> float:
        return max(0.0, event.base * mult * (1.0 - mit) - flat) * vuln

    return (1.0 - p) * branch(1.0) + p * branch(event.crit_mult)


def effective_health(max_hp: float, defender: DefenderProfile, dtype: DamageType, attacker_level: int = 1) -> float:
    """Raw damage needed to kill a defender of ``max_hp`` (ignores flat reduction)."""

    if max_hp <= 0:
        raise ValueError("max_hp must be > 0")
    probe = DamageEvent(base=1.0, dtype=dtype, attacker_level=attacker_level, can_crit=False)
    mit = mitigation_fraction(probe, defender)
    vuln = 1.0 if dtype is DamageType.TRUE else defender.vulnerability
    return max_hp / ((1.0 - mit) * vuln)
