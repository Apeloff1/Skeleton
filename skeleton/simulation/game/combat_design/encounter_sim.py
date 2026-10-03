"""Deterministic encounter simulator: player skill vs. a telegraphed attack rotation.

A player profile draws a reaction time per telegraph from a seeded,
bounded near-normal distribution (Irwin-Hall n=4). The hit is avoided when
reaction + escape (or a dodge commit) fits inside the windup. Player damage
flows continuously at ``dps * efficiency``.

Properties the model guarantees (and the tests pin):

* same inputs + seed -> same outcome digest;
* a faster-reacting, higher-efficiency profile never clears less often;
* a harder tier never clears more often;
* an unreadable lethal telegraph cannot be beaten by any profile.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from skeleton.simulation.game.mechanics_depth.tick_clock import SeededEntropy

from .damage import ARMOR_BASE, ARMOR_K, MAX_ARMOR_DR, MAX_RESIST, VARIANCE_BAND
from .difficulty import (
    BUDGET_COST,
    CORE_DPS_EFFICIENCY,
    TIER_SCALING,
    TTK_TARGETS_S,
    DifficultyTier,
)
from .telegraph import (
    DEFAULT_MOVE_SPEED_MPS,
    HUMAN_REACTION_MS,
    MIN_PATTERN_GAP_MS,
    TIER_RULES,
    AttackTelegraph,
    escape_time_ms,
)

DODGE_COMMIT_MS = 150
ATTACK_GAP_MS = 1500
MIN_REACTION_MS = 120
MAX_ROTATION = 64
MAX_ENEMY_HP = 1e9
MAX_SIM_TIME_MS = 3_600_000
_IRWIN_HALL_SD = math.sqrt(4.0 / 12.0)


@dataclass(frozen=True)
class SkillProfile:
    name: str
    reaction_mean_ms: float
    reaction_sd_ms: float
    dps_efficiency: float

    def __post_init__(self) -> None:
        if not (100 <= self.reaction_mean_ms <= 2000 and 0 <= self.reaction_sd_ms <= 500):
            raise ValueError("reaction stats out of bounds")
        if not (0.05 <= self.dps_efficiency <= 1.0):
            raise ValueError("dps efficiency out of bounds")


CASUAL = SkillProfile("casual", 480.0, 90.0, 0.6)
CORE = SkillProfile("core", 330.0, 60.0, CORE_DPS_EFFICIENCY)
EXPERT = SkillProfile("expert", 240.0, 35.0, 0.95)


@dataclass(frozen=True)
class EncounterOutcome:
    cleared: bool
    reason: str
    time_ms: int
    player_hp_fraction: float
    hits_taken: int
    dodges: int
    attacks: int
    digest: str


def sample_reaction_ms(profile: SkillProfile, entropy: SeededEntropy) -> float:
    s = sum(entropy.unit() for _ in range(4))
    z = (s - 2.0) / _IRWIN_HALL_SD
    return max(float(MIN_REACTION_MS), profile.reaction_mean_ms + profile.reaction_sd_ms * z)


def simulate_encounter(
    *,
    enemy_hp: float,
    rotation: Sequence[AttackTelegraph],
    player_max_hp: float,
    player_dps: float,
    profile: SkillProfile,
    tier: DifficultyTier = DifficultyTier.NORMAL,
    seed: int = 0,
    max_time_ms: int = 900_000,
    move_speed_mps: float = DEFAULT_MOVE_SPEED_MPS,
) -> EncounterOutcome:
    if not (0 < enemy_hp <= MAX_ENEMY_HP):
        raise ValueError("enemy_hp out of bounds")
    if not (1 <= len(rotation) <= MAX_ROTATION):
        raise ValueError("rotation size out of bounds")
    if player_max_hp <= 0 or player_dps <= 0:
        raise ValueError("player stats must be > 0")
    if not (1 <= max_time_ms <= MAX_SIM_TIME_MS):
        raise ValueError("max_time_ms out of bounds")
    scaling = TIER_SCALING[tier]
    scaled = [t.scaled(scaling.windup_scale, scaling.enemy_damage_mult) for t in rotation]
    entropy = SeededEntropy(seed)
    enemy = enemy_hp * scaling.enemy_hp_mult
    player = float(player_max_hp)
    eff_dps = player_dps * profile.dps_efficiency
    t = 0
    hits = dodges = attacks = 0
    records: List[Dict[str, Any]] = []
    reason = "timeout"
    i = 0
    while t < max_time_ms:
        tel = scaled[i % len(scaled)]
        i += 1
        reaction = sample_reaction_ms(profile, entropy)
        if tel.escape_distance_m > 0:
            need = reaction + escape_time_ms(tel.escape_distance_m, move_speed_mps)
        else:
            need = reaction + DODGE_COMMIT_MS
        resolve = tel.windup_ms + tel.active_ms
        enemy -= eff_dps * resolve / 1000.0
        if enemy <= 0:
            t += resolve
            reason = "cleared"
            break
        attacks += 1
        dodged = need <= tel.windup_ms
        if dodged:
            dodges += 1
        else:
            hits += 1
            player -= tel.damage_fraction * player_max_hp
        records.append({"a": tel.name, "r": round(reaction, 3), "d": dodged})
        if player <= 1e-9:
            t += resolve
            reason = "player_dead"
            break
        cycle = tel.total_ms + ATTACK_GAP_MS
        enemy -= eff_dps * (cycle - resolve) / 1000.0
        t += cycle
        if enemy <= 0:
            reason = "cleared"
            break
    body = json.dumps(
        {"seed": seed, "tier": tier.value, "profile": profile.name, "reason": reason, "t": t, "records": records},
        sort_keys=True,
    )
    return EncounterOutcome(
        cleared=reason == "cleared",
        reason=reason,
        time_ms=t,
        player_hp_fraction=max(0.0, player / player_max_hp),
        hits_taken=hits,
        dodges=dodges,
        attacks=attacks,
        digest=hashlib.sha256(body.encode()).hexdigest(),
    )


def clear_rate(n_seeds: int, **kwargs: Any) -> float:
    """Fraction of seeds ``0..n_seeds-1`` that clear the encounter."""

    if not (1 <= n_seeds <= 10_000):
        raise ValueError("n_seeds out of bounds")
    if "seed" in kwargs:
        raise ValueError("clear_rate owns the seed")
    wins = sum(1 for s in range(n_seeds) if simulate_encounter(seed=s, **kwargs).cleared)
    return wins / n_seeds


def balance_table() -> Dict[str, Any]:
    """JSON-serialisable snapshot of every tuning constant (for docs/diffs/review)."""

    def _num(x: float) -> Any:
        return None if math.isinf(x) else x

    return {
        "damage": {
            "armor_k": ARMOR_K,
            "armor_base": ARMOR_BASE,
            "max_armor_dr": MAX_ARMOR_DR,
            "max_resist": MAX_RESIST,
            "variance_band": VARIANCE_BAND,
        },
        "telegraph": {
            "human_reaction_ms": HUMAN_REACTION_MS,
            "min_pattern_gap_ms": MIN_PATTERN_GAP_MS,
            "tiers": {
                tier.value: {
                    "min_windup_ms": r.min_windup_ms,
                    "min_channels": r.min_channels,
                    "requires_audio": r.requires_audio,
                    "max_damage_fraction": _num(r.max_damage_fraction),
                    "min_recovery_ratio": r.min_recovery_ratio,
                }
                for tier, r in TIER_RULES.items()
            },
        },
        "difficulty": {
            tier.value: {
                "enemy_hp_mult": s.enemy_hp_mult,
                "enemy_damage_mult": s.enemy_damage_mult,
                "windup_scale": s.windup_scale,
            }
            for tier, s in TIER_SCALING.items()
        },
        "ttk_targets_s": {a.value: list(band) for a, band in TTK_TARGETS_S.items()},
        "budget_cost": {a.value: c for a, c in BUDGET_COST.items()},
        "skill_profiles": {
            p.name: {"reaction_mean_ms": p.reaction_mean_ms, "reaction_sd_ms": p.reaction_sd_ms, "dps_efficiency": p.dps_efficiency}
            for p in (CASUAL, CORE, EXPERT)
        },
        "sim": {"dodge_commit_ms": DODGE_COMMIT_MS, "attack_gap_ms": ATTACK_GAP_MS, "min_reaction_ms": MIN_REACTION_MS},
    }
