"""Structural checks against the GamePlan shape.

GamePlan (``skeleton.forge.ai_builder.game_plan.v1``)::

    schema, title, start_level, goal_levels[str], systems[str]
    player:     {hp > 0, dps > 0}
    assets:     [{id, kind}]
    scenes:     [{id, assets[str]}]
    levels:     [{id, scene, exits[str], encounters[str]}]
    encounters: [{id, system, enemy_hp > 0, enemy_dps >= 0}]
    triggers:   [{id, on: str, emits[str], once?: bool}]   (optional)
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from ._common import err

GAME_PLAN_SCHEMA = "skeleton.forge.ai_builder.game_plan.v1"
RULE = "schema"

_STR, _STRS, _POS, _NONNEG, _BOOL = "str", "strs", "pos", "nonneg", "bool"
_SECTIONS: dict[str, dict[str, str]] = {
    "assets": {"id": _STR, "kind": _STR},
    "scenes": {"id": _STR, "assets": _STRS},
    "levels": {"id": _STR, "scene": _STR, "exits": _STRS, "encounters": _STRS},
    "encounters": {"id": _STR, "system": _STR, "enemy_hp": _POS, "enemy_dps": _NONNEG},
    "triggers": {"id": _STR, "on": _STR, "emits": _STRS},
}
_OPTIONAL_SECTIONS = {"triggers"}


def _ok(kind: str, v: Any) -> bool:
    if kind == _STR:
        return isinstance(v, str) and bool(v.strip())
    if kind == _STRS:
        return isinstance(v, list) and all(isinstance(x, str) and x for x in v)
    if kind == _BOOL:
        return isinstance(v, bool)
    num = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    return num and (v > 0 if kind == _POS else v >= 0)


def check_schema(plan: Any) -> list:
    if not isinstance(plan, Mapping):
        return [err(RULE, "plan must be an object")]
    out = []
    if plan.get("schema") != GAME_PLAN_SCHEMA:
        out.append(err(RULE, f"schema must be {GAME_PLAN_SCHEMA!r}"))
    for key, kind in (("title", _STR), ("start_level", _STR), ("goal_levels", _STRS), ("systems", _STRS)):
        if not _ok(kind, plan.get(key)):
            out.append(err(RULE, f"{key}: expected {kind}"))
    if isinstance(plan.get("goal_levels"), list) and not plan["goal_levels"]:
        out.append(err(RULE, "goal_levels: at least one goal"))
    player = plan.get("player")
    if not isinstance(player, Mapping):
        out.append(err(RULE, "player: expected object"))
    else:
        for key in ("hp", "dps"):
            if not _ok(_POS, player.get(key)):
                out.append(err(RULE, f"player.{key}: expected pos"))
    for section, fields in _SECTIONS.items():
        value = plan.get(section)
        if value is None and section in _OPTIONAL_SECTIONS:
            continue
        if not isinstance(value, list) or (not value and section not in _OPTIONAL_SECTIONS):
            out.append(err(RULE, f"{section}: expected non-empty list"))
            continue
        seen: set[str] = set()
        for i, entry in enumerate(value):
            if not isinstance(entry, Mapping):
                out.append(err(RULE, f"{section}[{i}]: expected object"))
                continue
            for name, kind in fields.items():
                if not _ok(kind, entry.get(name)):
                    out.append(err(RULE, f"{section}[{i}].{name}: expected {kind}"))
            if section == "triggers" and "once" in entry and not _ok(_BOOL, entry["once"]):
                out.append(err(RULE, f"{section}[{i}].once: expected bool"))
            eid = entry.get("id")
            if isinstance(eid, str):
                if eid in seen:
                    out.append(err(RULE, f"{section}: duplicate id {eid!r}"))
                seen.add(eid)
    return out
