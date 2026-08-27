"""Era dialects for the Forge — TTK-consistent numeric packs.

A Forge blueprint can declare ``era`` on the materialise call. The pack
supplies player/heat/session/jeeves numbers and compiles enemy HP from
target time-to-kill × primary DPS so the emitted game is internally
consistent instead of a pile of unrelated constants.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

ERA_IDS: List[str] = [
    "extraction_now",
    "soulslike",
    "boomer_shooter",
    "arcade_golden_age",
    "cozy_wholesome",
    "modern_aaa",
    "horror_survival",
    "indie_experimental",
    "metroidvania",
    "roguelike",
    "jrpg",
    "crpg",
    "immersive_sim",
    "stealth",
    "tactics_grid",
    "fighting_game",
    "bullet_heaven",
    "deckbuilder",
    "battle_royale",
    "mmorpg",
    "visual_novel",
    "walking_sim",
    "grand_strategy",
    "city_builder",
]

_BASE: Dict[str, Any] = {
    "player": {"speed": 195.0, "sprint_multiplier": 1.48, "max_health": 100.0, "i_frame_ms": 350.0},
    "heat": {
        "max_heat": 100.0, "passive_cool": 7.5, "critical_ratio": 0.78,
        "kinetic_heat": 6.2, "energy_heat": 11.5, "sprint_heat_per_sec": 11.0,
    },
    "ttk": {"trash": 1.1, "elite": 4.5, "boss": 60.0, "player_glass": 1.8},
    "session": {"collapse_max": 320.0, "room_count_min": 8, "room_count_max": 15},
    "jeeves": {"heat_rising": 0.65, "heat_critical": 0.92, "advice_cooldown_normal": 4.5, "confidence_base": 0.72},
    "meta": {"philosophy": "risk_session_value", "permadeath": 0.75},
}

_DELTA: Dict[str, Dict[str, Any]] = {
    "soulslike": {
        "player": {"speed": 155.0, "sprint_multiplier": 1.25, "i_frame_ms": 180.0},
        "heat": {"passive_cool": 5.5, "critical_ratio": 0.70, "sprint_heat_per_sec": 14.0},
        "ttk": {"trash": 1.5, "elite": 6.0, "boss": 120.0, "player_glass": 1.0},
        "session": {"collapse_max": 480.0},
        "jeeves": {"heat_rising": 0.55, "heat_critical": 0.85, "confidence_base": 0.60},
        "meta": {"philosophy": "loss_forward", "permadeath": 0.85},
    },
    "boomer_shooter": {
        "player": {"speed": 220.0, "sprint_multiplier": 1.60, "i_frame_ms": 200.0},
        "heat": {"passive_cool": 9.0, "critical_ratio": 0.82},
        "ttk": {"trash": 0.4, "elite": 2.0, "boss": 25.0, "player_glass": 1.0},
        "session": {"collapse_max": 200.0},
        "meta": {"philosophy": "movement_gun_poetry", "permadeath": 0.50},
    },
    "arcade_golden_age": {
        "player": {"speed": 160.0, "sprint_multiplier": 1.0, "max_health": 3.0, "i_frame_ms": 1200.0},
        "heat": {"max_heat": 1.0, "passive_cool": 99.0, "critical_ratio": 1.0, "kinetic_heat": 0.0},
        "ttk": {"trash": 0.3, "elite": 2.0, "boss": 15.0, "player_glass": 0.4},
        "session": {"collapse_max": 90.0},
        "meta": {"philosophy": "score_attack", "permadeath": 1.0},
    },
    "cozy_wholesome": {
        "player": {"speed": 140.0, "sprint_multiplier": 1.2, "i_frame_ms": 800.0},
        "heat": {"max_heat": 50.0, "passive_cool": 12.0, "critical_ratio": 0.95, "kinetic_heat": 1.0},
        "ttk": {"trash": 3.0, "elite": 8.0, "boss": 30.0, "player_glass": 10.0},
        "session": {"collapse_max": 9999.0},
        "jeeves": {"confidence_base": 0.90},
        "meta": {"philosophy": "low_stress_mastery", "permadeath": 0.0},
    },
    "modern_aaa": {
        "player": {"speed": 200.0, "sprint_multiplier": 1.50, "i_frame_ms": 350.0},
        "ttk": {"trash": 1.0, "elite": 4.0, "boss": 70.0, "player_glass": 2.0},
        "session": {"collapse_max": 360.0},
        "meta": {"philosophy": "assisted_mastery", "permadeath": 0.15},
    },
    "horror_survival": {
        "player": {"speed": 150.0, "sprint_multiplier": 1.30, "i_frame_ms": 250.0},
        "heat": {"passive_cool": 5.0, "critical_ratio": 0.70, "sprint_heat_per_sec": 15.0},
        "ttk": {"trash": 2.5, "elite": 8.0, "boss": 90.0, "player_glass": 0.8},
        "session": {"collapse_max": 600.0},
        "jeeves": {"confidence_base": 0.55},
        "meta": {"philosophy": "scarcity_dread", "permadeath": 0.70},
    },
    "indie_experimental": {
        "player": {"speed": 210.0, "sprint_multiplier": 1.70, "max_health": 80.0},
        "ttk": {"trash": 0.8, "elite": 5.0, "boss": 45.0, "player_glass": 1.3},
        "session": {"collapse_max": 240.0},
        "meta": {"philosophy": "author_expression", "permadeath": 0.50},
    },

    "metroidvania": {
        "player": {"speed": 170.0, "sprint_multiplier": 1.35, "i_frame_ms": 220.0},
        "ttk": {"trash": 0.9, "elite": 5.0, "boss": 80.0, "player_glass": 1.5},
        "session": {"collapse_max": 900.0, "room_count_min": 20, "room_count_max": 80},
        "meta": {"philosophy": "ability_gated_backtrack", "permadeath": 0.10},
    },
    "roguelike": {
        "player": {"speed": 180.0, "sprint_multiplier": 1.40},
        "ttk": {"trash": 0.8, "elite": 3.5, "boss": 40.0, "player_glass": 0.9},
        "session": {"collapse_max": 1800.0},
        "meta": {"philosophy": "run_knowledge", "permadeath": 1.0},
    },
    "jrpg": {
        "player": {"speed": 130.0, "sprint_multiplier": 1.15, "max_health": 200.0},
        "heat": {"passive_cool": 10.0, "kinetic_heat": 3.0},
        "ttk": {"trash": 4.0, "elite": 12.0, "boss": 180.0, "player_glass": 8.0},
        "session": {"collapse_max": 3600.0},
        "meta": {"philosophy": "party_attrition", "permadeath": 0.05},
    },
    "crpg": {
        "player": {"speed": 140.0, "sprint_multiplier": 1.20},
        "ttk": {"trash": 3.0, "elite": 10.0, "boss": 150.0, "player_glass": 5.0},
        "session": {"collapse_max": 2400.0},
        "meta": {"philosophy": "build_expression", "permadeath": 0.20},
    },
    "immersive_sim": {
        "player": {"speed": 165.0, "sprint_multiplier": 1.30, "i_frame_ms": 200.0},
        "ttk": {"trash": 1.8, "elite": 6.0, "boss": 70.0, "player_glass": 1.4},
        "session": {"collapse_max": 1200.0},
        "jeeves": {"confidence_base": 0.50},
        "meta": {"philosophy": "systemic_emergence", "permadeath": 0.25},
    },
    "stealth": {
        "player": {"speed": 145.0, "sprint_multiplier": 1.55, "i_frame_ms": 150.0},
        "heat": {"sprint_heat_per_sec": 18.0, "critical_ratio": 0.60},
        "ttk": {"trash": 0.5, "elite": 3.0, "boss": 50.0, "player_glass": 0.6},
        "session": {"collapse_max": 600.0},
        "meta": {"philosophy": "unseen_agency", "permadeath": 0.40},
    },
    "tactics_grid": {
        "player": {"speed": 100.0, "sprint_multiplier": 1.0, "i_frame_ms": 0.0},
        "ttk": {"trash": 2.0, "elite": 6.0, "boss": 90.0, "player_glass": 3.0},
        "session": {"collapse_max": 1800.0},
        "meta": {"philosophy": "positional_certainty", "permadeath": 0.30},
    },
    "fighting_game": {
        "player": {"speed": 240.0, "sprint_multiplier": 1.10, "i_frame_ms": 80.0},
        "heat": {"max_heat": 100.0, "passive_cool": 20.0, "critical_ratio": 0.90, "kinetic_heat": 8.0},
        "ttk": {"trash": 0.6, "elite": 2.5, "boss": 20.0, "player_glass": 0.7},
        "session": {"collapse_max": 99.0},
        "meta": {"philosophy": "frame_truth", "permadeath": 0.0},
    },
    "bullet_heaven": {
        "player": {"speed": 200.0, "sprint_multiplier": 1.25, "i_frame_ms": 400.0},
        "ttk": {"trash": 0.2, "elite": 1.5, "boss": 35.0, "player_glass": 1.2},
        "session": {"collapse_max": 1800.0},
        "meta": {"philosophy": "build_as_firehose", "permadeath": 1.0},
    },
    "deckbuilder": {
        "player": {"speed": 150.0, "sprint_multiplier": 1.10},
        "ttk": {"trash": 2.5, "elite": 7.0, "boss": 80.0, "player_glass": 3.0},
        "session": {"collapse_max": 2400.0},
        "meta": {"philosophy": "card_as_verb", "permadeath": 0.90},
    },
    "battle_royale": {
        "player": {"speed": 190.0, "sprint_multiplier": 1.55},
        "heat": {"sprint_heat_per_sec": 12.0},
        "ttk": {"trash": 0.9, "elite": 3.0, "boss": 25.0, "player_glass": 1.1},
        "session": {"collapse_max": 1200.0},
        "meta": {"philosophy": "shrinking_agency", "permadeath": 1.0},
    },
    "mmorpg": {
        "player": {"speed": 175.0, "sprint_multiplier": 1.40, "max_health": 150.0},
        "ttk": {"trash": 2.0, "elite": 8.0, "boss": 300.0, "player_glass": 4.0},
        "session": {"collapse_max": 7200.0},
        "meta": {"philosophy": "raid_as_social_machine", "permadeath": 0.05},
    },
    "visual_novel": {
        "player": {"speed": 80.0, "sprint_multiplier": 1.0, "max_health": 1.0, "i_frame_ms": 0.0},
        "heat": {"max_heat": 1.0, "kinetic_heat": 0.0, "passive_cool": 99.0},
        "ttk": {"trash": 8.0, "elite": 8.0, "boss": 8.0, "player_glass": 99.0},
        "session": {"collapse_max": 9999.0},
        "meta": {"philosophy": "choice_as_combat", "permadeath": 0.0},
    },
    "walking_sim": {
        "player": {"speed": 110.0, "sprint_multiplier": 1.15, "i_frame_ms": 2000.0},
        "heat": {"kinetic_heat": 0.0, "passive_cool": 99.0},
        "ttk": {"trash": 12.0, "elite": 12.0, "boss": 12.0, "player_glass": 99.0},
        "session": {"collapse_max": 9999.0},
        "meta": {"philosophy": "presence", "permadeath": 0.0},
    },
    "grand_strategy": {
        "player": {"speed": 90.0, "sprint_multiplier": 1.0},
        "ttk": {"trash": 10.0, "elite": 40.0, "boss": 600.0, "player_glass": 20.0},
        "session": {"collapse_max": 99999.0},
        "meta": {"philosophy": "systems_as_history", "permadeath": 0.40},
    },
    "city_builder": {
        "player": {"speed": 100.0, "sprint_multiplier": 1.0},
        "ttk": {"trash": 15.0, "elite": 40.0, "boss": 200.0, "player_glass": 30.0},
        "session": {"collapse_max": 99999.0},
        "meta": {"philosophy": "growth_under_constraint", "permadeath": 0.10},
    },
}


def _merge(base: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for section, vals in delta.items():
        if isinstance(vals, dict) and isinstance(out.get(section), dict):
            merged = dict(out[section])
            merged.update(vals)
            out[section] = merged
        else:
            out[section] = deepcopy(vals)
    return out


def era_pack(era: str) -> Dict[str, Any]:
    name = era if era in ERA_IDS else "extraction_now"
    pack = _merge(_BASE, _DELTA.get(name, {}))
    pack["era"] = name
    return pack


def primary_dps(pack: Dict[str, Any]) -> float:
    """Kinetic shot DPS used as the HP compiler numerator."""
    # 18 dmg * 360 rpm / 60 = 108 baseline, scaled by player speed as a motor proxy
    speed = float(pack["player"].get("speed") or 180.0)
    return round(18.0 * (360.0 / 60.0) * (speed / 195.0), 1)


def compile_era(era: str) -> Dict[str, Any]:
    pack = era_pack(era)
    dps = primary_dps(pack)
    ttk = pack["ttk"]
    pack["primary_dps"] = dps
    pack["enemies"] = [
        {"id": "trash", "hp": round(dps * float(ttk["trash"]), 1), "ttk_target": ttk["trash"]},
        {"id": "elite", "hp": round(dps * float(ttk["elite"]), 1), "ttk_target": ttk["elite"]},
        {"id": "boss", "hp": round(dps * float(ttk["boss"]), 1), "ttk_target": ttk["boss"]},
    ]
    pack["recipes"] = [
        {"id": "kinetic_basic", "family": "kinetic", "damage": 18, "heat": pack["heat"]["kinetic_heat"], "rpm": 360,
         "parts": ["barrel_std", "frame_light", "mag_std"]},
        {"id": "kinetic_heavy", "family": "kinetic", "damage": 32, "heat": round(pack["heat"]["kinetic_heat"] * 1.4, 1),
         "rpm": 220, "parts": ["barrel_heavy", "frame_std", "mag_drum"]},
        {"id": "energy_pulse", "family": "energy", "damage": 28, "heat": pack["heat"]["energy_heat"], "rpm": 180,
         "parts": ["emitter_pulse", "frame_std", "cell_basic"]},
    ]
    return pack


def list_eras() -> List[str]:
    return list(ERA_IDS)
