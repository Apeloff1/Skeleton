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
