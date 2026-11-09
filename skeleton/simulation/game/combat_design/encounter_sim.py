"""Deterministic encounter simulator: player skill vs. a telegraphed attack rotation.

A player profile draws a reaction time per telegraph from a seeded,
bounded near-normal distribution (Irwin-Hall n=4). The hit is avoided when
reaction + escape (or a dodge commit) fits inside the windup. Player damage
flows continuously at ``dps * efficiency``.

Properties the model guarantees (and the tests pin):

* same inputs + seed -> same outcome digest;
* a faster-reacting, higher-efficiency profile never clears less often;
* a harder tier never clears more often;
* the deadline never resolves a future attack or a future clear.

These are design simulations, not guarantees about real human play. High DPS
may kill an enemy before even an unreadable lethal attack resolves. Readability
must therefore be audited separately from clear rates.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
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
        if not isinstance(self.name, str) or not 1 <= len(self.name) <= 64:
            raise ValueError("profile name out of bounds")
        for value in (self.reaction_mean_ms, self.reaction_sd_ms, self.dps_efficiency):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("profile stats must be finite numbers")
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
    for value in (enemy_hp, player_max_hp, player_dps, move_speed_mps):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1e-6 <= value <= MAX_ENEMY_HP:
            raise ValueError("encounter stats must be finite positive bounded numbers")
    if type(seed) is not int or not 0 <= seed <= 2_147_483_647:
        raise ValueError("seed out of bounds")
    if not isinstance(tier, DifficultyTier) or not isinstance(profile, SkillProfile):
        raise ValueError("typed tier and skill profile required")
    if not (0 < enemy_hp <= MAX_ENEMY_HP):
        raise ValueError("enemy_hp out of bounds")
    if not isinstance(rotation, (list, tuple)) or not (1 <= len(rotation) <= MAX_ROTATION) or any(not isinstance(tel, AttackTelegraph) for tel in rotation):
        raise ValueError("rotation size out of bounds")
    if player_max_hp <= 0 or player_dps <= 0:
        raise ValueError("player stats must be > 0")
    if type(max_time_ms) is not int or not (1 <= max_time_ms <= MAX_SIM_TIME_MS):
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
        available = min(resolve, max_time_ms - t)
        kill_ms = math.ceil(enemy * 1000.0 / eff_dps)
        if kill_ms <= available:
            t += kill_ms
            reason = "cleared"
            break
        enemy -= eff_dps * available / 1000.0
        t += available
        if available < resolve:
            break  # deadline: no attack or recovery can happen afterwards
        attacks += 1
        dodged = need <= tel.windup_ms
        if dodged:
            dodges += 1
        else:
            hits += 1
            player -= tel.damage_fraction * player_max_hp
        records.append({"a": tel.name, "r": round(reaction, 3), "d": dodged})
        if player <= 1e-9:
            reason = "player_dead"
            break
        cycle = tel.total_ms + ATTACK_GAP_MS
        available = min(cycle - resolve, max_time_ms - t)
        kill_ms = math.ceil(enemy * 1000.0 / eff_dps)
        if kill_ms <= available:
            t += kill_ms
            reason = "cleared"
            break
        enemy -= eff_dps * available / 1000.0
        t += available
    body = json.dumps(
        {
            "schema": "combat.encounter.v2", "seed": seed, "tier": tier.value,
            "scaling": asdict(scaling),
            "profile": asdict(profile), "enemy_hp": enemy_hp,
            "player_max_hp": player_max_hp, "player_dps": player_dps,
            "max_time_ms": max_time_ms, "move_speed_mps": move_speed_mps,
            "rotation": [_telegraph_record(tel) for tel in rotation],
            "reason": reason, "t": t, "records": records,
            "remaining_player_hp": max(0.0, player),
            "hits": hits, "dodges": dodges, "attacks": attacks,
        },
        sort_keys=True, allow_nan=False,
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

    if type(n_seeds) is not int or not (1 <= n_seeds <= 10_000):
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


def _telegraph_record(tel: AttackTelegraph) -> dict[str, Any]:
    return {
        **asdict(tel), "tier": tel.tier.value,
        "channels": sorted(c.value for c in tel.channels),
    }


def evaluate_encounter_design(
    *, enemy_hp: float, rotation: Sequence[AttackTelegraph],
    player_max_hp: float, player_dps: float,
    n_seeds: int = 32, max_time_ms: int = 120_000,
    move_speed_mps: float = DEFAULT_MOVE_SPEED_MPS,
) -> dict[str, Any]:
    """Measured deterministic cohort matrix plus scaled readability findings.

    Same seed cohort is reused across 4 tiers and 3 profiles. This is a
    designer's simulation report, not measured human playtesting or an
    automatic balance/promotion decision. Readability audits are surfaced
    independently from success rates: survivable is not necessarily fair.
    """
    from .telegraph import PatternEntry, audit_pattern

    if type(n_seeds) is not int or not 1 <= n_seeds <= 128:
        raise ValueError("design report requires 1..128 seeds")
    if type(max_time_ms) is not int or not 1 <= max_time_ms <= 300_000:
        raise ValueError("design report deadline must be 1..300000ms")
    # Validate all inputs before even constructing the report.
    simulate_encounter(
        enemy_hp=enemy_hp, rotation=rotation, player_max_hp=player_max_hp,
        player_dps=player_dps, profile=CORE, max_time_ms=max_time_ms,
        move_speed_mps=move_speed_mps,
    )
    rows = []
    for tier in DifficultyTier:
        scaling = TIER_SCALING[tier]
        authored = [tel.scaled(scaling.windup_scale, scaling.enemy_damage_mult) for tel in rotation]
        timeline = []
        start = 0
        # Two cycles audit the wraparound seam, not only the first rotation.
        for tel in authored * 2:
            timeline.append(PatternEntry(start, tel))
            start += tel.total_ms + ATTACK_GAP_MS
        findings = [asdict(v) for v in audit_pattern(timeline, move_speed_mps=move_speed_mps)]
        for profile in (CASUAL, CORE, EXPERT):
            outcomes = [simulate_encounter(
                enemy_hp=enemy_hp, rotation=rotation, player_max_hp=player_max_hp,
                player_dps=player_dps, profile=profile, tier=tier, seed=seed,
                max_time_ms=max_time_ms, move_speed_mps=move_speed_mps,
            ) for seed in range(n_seeds)]
            wins = [o for o in outcomes if o.cleared]
            times = sorted(o.time_ms for o in wins)
            rows.append({
                "tier": tier.value, "profile": profile.name,
                "trials": n_seeds, "clears": len(wins), "clear_rate": len(wins) / n_seeds,
                "deaths": sum(o.reason == "player_dead" for o in outcomes),
                "timeouts": sum(o.reason == "timeout" for o in outcomes),
                "mean_clear_ms": sum(times) / len(times) if times else None,
                "p95_clear_ms": times[math.ceil(len(times) * 0.95) - 1] if times else None,
                "mean_hits_taken": sum(o.hits_taken for o in outcomes) / n_seeds,
                "mean_remaining_hp_fraction": sum(o.player_hp_fraction for o in outcomes) / n_seeds,
                "readability_violations": findings,
                "outcome_digests": [o.digest for o in outcomes],
            })
    report = {
        "schema": "combat.design_report.v1", "seed_cohort": [0, n_seeds - 1],
        "model": "continuous_player_dps_telegraph_end_resolution",
        "deadline_ms": max_time_ms,
        "inputs": {"enemy_hp": enemy_hp, "player_max_hp": player_max_hp,
                   "player_dps": player_dps, "move_speed_mps": move_speed_mps,
                   "rotation": [_telegraph_record(tel) for tel in rotation]},
        "tuning": balance_table(),
        "rows": rows, "human_playtesting": False, "auto_apply": False,
    }
    report["digest"] = hashlib.sha256(json.dumps(
        report, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    return report
