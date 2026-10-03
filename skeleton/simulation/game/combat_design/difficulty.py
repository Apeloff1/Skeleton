"""Difficulty tiers, time-to-kill targets, zone intensity curves, encounter budgets.

Principles:

* Tiers scale enemy HP and damage up and windups down, monotonically.
  Windups never drop below the telegraph tier floor (see :mod:`.telegraph`).
* HP is derived from time-to-kill (TTK) targets, not hand-typed: a core player
  at NORMAL hits the midpoint of each archetype's TTK band exactly.
* Zone pacing is a rising sawtooth: an overall upward trend, no spikes, a
  breather after every climb, and the boss as the strict peak.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

CORE_DPS_EFFICIENCY = 0.8
MAX_CURVE_LEN = 256


class DifficultyTier(str, Enum):
    STORY = "story"
    NORMAL = "normal"
    HEROIC = "heroic"
    MYTHIC = "mythic"


TIER_ORDER: Tuple[DifficultyTier, ...] = (
    DifficultyTier.STORY,
    DifficultyTier.NORMAL,
    DifficultyTier.HEROIC,
    DifficultyTier.MYTHIC,
)


@dataclass(frozen=True)
class TierScaling:
    enemy_hp_mult: float
    enemy_damage_mult: float
    windup_scale: float


TIER_SCALING: Dict[DifficultyTier, TierScaling] = {
    DifficultyTier.STORY: TierScaling(0.6, 0.5, 1.4),
    DifficultyTier.NORMAL: TierScaling(1.0, 1.0, 1.0),
    DifficultyTier.HEROIC: TierScaling(1.4, 1.35, 0.9),
    DifficultyTier.MYTHIC: TierScaling(2.0, 1.8, 0.8),
}


class Archetype(str, Enum):
    TRASH = "trash"
    ELITE = "elite"
    MINIBOSS = "miniboss"
    BOSS = "boss"


# Solo time-to-kill bands in seconds, authored for a core player at NORMAL.
TTK_TARGETS_S: Dict[Archetype, Tuple[float, float]] = {
    Archetype.TRASH: (3.0, 6.0),
    Archetype.ELITE: (12.0, 20.0),
    Archetype.MINIBOSS: (45.0, 75.0),
    Archetype.BOSS: (180.0, 360.0),
}

BUDGET_COST: Dict[Archetype, int] = {
    Archetype.TRASH: 1,
    Archetype.ELITE: 4,
    Archetype.MINIBOSS: 10,
    Archetype.BOSS: 30,
}

# Minimum zone intensity before an archetype may appear, and per-encounter caps.
ARCHETYPE_GATE: Dict[Archetype, float] = {
    Archetype.TRASH: 0.0,
    Archetype.ELITE: 0.3,
    Archetype.MINIBOSS: 0.6,
    Archetype.BOSS: 0.95,
}
ARCHETYPE_CAP: Dict[Archetype, Optional[int]] = {
    Archetype.TRASH: None,
    Archetype.ELITE: None,
    Archetype.MINIBOSS: 2,
    Archetype.BOSS: 1,
}


def time_to_kill_s(hp: float, dps: float) -> float:
    if hp <= 0 or dps <= 0:
        raise ValueError("hp and dps must be > 0")
    return hp / dps


def archetype_hp(archetype: Archetype, player_dps: float, tier: DifficultyTier = DifficultyTier.NORMAL, party_size: int = 1) -> float:
    """HP such that a core-efficiency party hits the TTK midpoint at NORMAL."""

    if player_dps <= 0 or player_dps > 1e7:
        raise ValueError("player_dps out of bounds")
    if not (1 <= party_size <= 40):
        raise ValueError("party_size out of bounds")
    lo, hi = TTK_TARGETS_S[archetype]
    mid = (lo + hi) / 2.0
    return mid * player_dps * CORE_DPS_EFFICIENCY * party_size * TIER_SCALING[tier].enemy_hp_mult


def build_zone_curve(
    n_encounters: int,
    *,
    start: float = 0.2,
    peak: float = 1.0,
    breather_every: int = 3,
    breather_drop: float = 0.15,
) -> Tuple[float, ...]:
    """Rising sawtooth: linear ramp with a dip every ``breather_every`` encounters; boss = peak."""

    if not (2 <= n_encounters <= MAX_CURVE_LEN):
        raise ValueError("n_encounters out of bounds")
    if not (0.0 < start < peak <= 1.5):
        raise ValueError("need 0 < start < peak <= 1.5")
    if breather_every < 2 or not (0.0 <= breather_drop <= 0.5):
        raise ValueError("bad breather settings")
    step = (peak - start) / (n_encounters - 1)
    values: List[float] = []
    for i in range(n_encounters):
        v = start + step * i
        if 0 < i < n_encounters - 1 and i % breather_every == 0:
            v = max(0.05, v - breather_drop)
        values.append(round(v, 6))
    values[-1] = peak
    return tuple(values)


def _slope(values: Sequence[float]) -> float:
    n = len(values)
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return num / den


def validate_curve(values: Sequence[float], *, max_step: float = 0.35, max_climb: int = 4) -> List[str]:
    """Return pacing violations for a zone intensity curve (empty list = healthy)."""

    out: List[str] = []
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return ["too_short"]
    if len(vals) > MAX_CURVE_LEN:
        return ["too_long"]
    if any(not (0.0 < v <= 1.5) for v in vals):
        out.append("out_of_range")
    if not all(vals[-1] > v for v in vals[:-1]):
        out.append("final_not_peak")
    if _slope(vals) <= 0:
        out.append("non_positive_trend")
    if any(b - a > max_step for a, b in zip(vals, vals[1:])):
        out.append("spike")
    run = 1
    longest = 1
    for a, b in zip(vals, vals[1:]):
        run = run + 1 if b > a else 1
        longest = max(longest, run)
    if longest > max_climb:
        out.append("no_breather")
    return out


def encounter_budget(intensity: float, party_size: int = 1, base_points: int = 40) -> int:
    """Threat points available to an encounter at a given intensity."""

    if not (0.0 <= intensity <= 1.5):
        raise ValueError("intensity out of bounds")
    if not (1 <= party_size <= 40) or not (1 <= base_points <= 10_000):
        raise ValueError("budget inputs out of bounds")
    return int(round(base_points * intensity * (1.0 + 0.75 * (party_size - 1))))


def compose_encounter(budget: int, intensity: float) -> Dict[Archetype, int]:
    """Greedy largest-first composition gated by intensity; total cost <= budget."""

    if budget < 0:
        raise ValueError("budget must be >= 0")
    if not (0.0 <= intensity <= 1.5):
        raise ValueError("intensity out of bounds")
    remaining = budget
    counts: Dict[Archetype, int] = {a: 0 for a in Archetype}
    for archetype in (Archetype.BOSS, Archetype.MINIBOSS, Archetype.ELITE, Archetype.TRASH):
        if intensity < ARCHETYPE_GATE[archetype]:
            continue
        cost = BUDGET_COST[archetype]
        n = remaining // cost
        cap = ARCHETYPE_CAP[archetype]
        if cap is not None:
            n = min(n, cap)
        counts[archetype] = n
        remaining -= n * cost
    return counts
