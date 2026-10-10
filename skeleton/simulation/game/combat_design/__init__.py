"""Combat design layer: damage model, telegraph readability, difficulty curves, encounter sim.

Extend-only companion to :mod:`skeleton.simulation.game.mechanics_depth`.
Everything here is deterministic (no ``random``, no wall clock) and bounded.
"""

from .damage import (
    ARMOR_BASE,
    ARMOR_K,
    MAX_ARMOR_DR,
    MAX_RESIST,
    VARIANCE_BAND,
    DamageEvent,
    DamageResult,
    DamageType,
    DefenderProfile,
    armor_damage_reduction,
    effective_health,
    expected_damage,
    mitigation_fraction,
    resolve_damage,
)
from .telegraph import (
    HUMAN_REACTION_MS,
    TIER_RULES,
    AttackTelegraph,
    PatternEntry,
    TelegraphChannel,
    ThreatTier,
    Violation,
    audit_pattern,
    audit_telegraph,
    escape_time_ms,
    is_readable,
    required_reaction_budget_ms,
)
from .difficulty import (
    BUDGET_COST,
    CORE_DPS_EFFICIENCY,
    TIER_SCALING,
    TTK_TARGETS_S,
    Archetype,
    DifficultyTier,
    TierScaling,
    archetype_hp,
    build_zone_curve,
    compose_encounter,
    encounter_budget,
    time_to_kill_s,
    validate_curve,
)
from .encounter_sim import (
    CASUAL,
    CORE,
    EXPERT,
    EncounterOutcome,
    SkillProfile,
    balance_table,
    evaluate_encounter_design,
    clear_rate,
    sample_reaction_ms,
    simulate_encounter,
)

__all__ = [
    "ARMOR_BASE", "ARMOR_K", "MAX_ARMOR_DR", "MAX_RESIST", "VARIANCE_BAND",
    "DamageEvent", "DamageResult", "DamageType", "DefenderProfile",
    "armor_damage_reduction", "effective_health", "expected_damage",
    "mitigation_fraction", "resolve_damage",
    "HUMAN_REACTION_MS", "TIER_RULES", "AttackTelegraph", "PatternEntry",
    "TelegraphChannel", "ThreatTier", "Violation", "audit_pattern",
    "audit_telegraph", "escape_time_ms", "is_readable", "required_reaction_budget_ms",
    "BUDGET_COST", "CORE_DPS_EFFICIENCY", "TIER_SCALING", "TTK_TARGETS_S",
    "Archetype", "DifficultyTier", "TierScaling", "archetype_hp",
    "build_zone_curve", "compose_encounter", "encounter_budget",
    "time_to_kill_s", "validate_curve",
    "CASUAL", "CORE", "EXPERT", "EncounterOutcome", "SkillProfile",
    "balance_table", "evaluate_encounter_design", "clear_rate", "sample_reaction_ms", "simulate_encounter",
]
