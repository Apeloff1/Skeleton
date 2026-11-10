"""Every asset, scene, system, level and encounter reference resolves."""
from __future__ import annotations

from typing import Any, Mapping

from ._common import err, ids, items, warn

RULE = "references"


def check_references(plan: Mapping[str, Any]) -> list:
    out = []
    assets, scenes, levels, encs = (ids(plan, k) for k in ("assets", "scenes", "levels", "encounters"))
    systems = {s for s in plan.get("systems") or [] if isinstance(s, str)}
    for sc in items(plan, "scenes"):
        for a in sc.get("assets") or []:
            if a not in assets:
                out.append(err(RULE, f"scene {sc.get('id')!r}: unknown asset {a!r}"))
    for lv in items(plan, "levels"):
        if lv.get("scene") not in scenes:
            out.append(err(RULE, f"level {lv.get('id')!r}: unknown scene {lv.get('scene')!r}"))
        for x in lv.get("exits") or []:
            if x not in levels:
                out.append(err(RULE, f"level {lv.get('id')!r}: unknown exit {x!r}"))
        for e in lv.get("encounters") or []:
            if e not in encs:
                out.append(err(RULE, f"level {lv.get('id')!r}: unknown encounter {e!r}"))
    for en in items(plan, "encounters"):
        if en.get("system") not in systems:
            out.append(err(RULE, f"encounter {en.get('id')!r}: unknown system {en.get('system')!r}"))
    if plan.get("start_level") not in levels:
        out.append(err(RULE, f"start_level {plan.get('start_level')!r} unknown"))
    for g in plan.get("goal_levels") or []:
        if g not in levels:
            out.append(err(RULE, f"goal level {g!r} unknown"))
    used_assets = {a for sc in items(plan, "scenes") for a in sc.get("assets") or []}
    for a in sorted(assets - used_assets):
        out.append(warn(RULE, f"asset {a!r} unused"))
    used_scenes = {lv.get("scene") for lv in items(plan, "levels")}
    for s in sorted(scenes - used_scenes):
        out.append(warn(RULE, f"scene {s!r} unused"))
    return out
