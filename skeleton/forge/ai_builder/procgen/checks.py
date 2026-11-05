"""Opt-in validation rules for procgen output.

Nothing here is registered with ``validate.score_plan``; default scoring is
unchanged. Callers opt in with :func:`check_procgen` (problems only) or
:func:`score_plan_procgen` (default verdict, downgraded to ``repair`` when a
procgen rule errors). Rules re-derive everything from the plan itself
(levels, exits, encounters, player), using ``plan["procgen"]`` only for the
lock/key placement, so hand edits after generation are caught.
"""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.forge.ai_builder.validate._common import err, items, warn
from skeleton.forge.ai_builder.validate.scoring import REPAIR, ACCEPT, Thresholds, Verdict, score_plan
from skeleton.forge.validator import Severity

from .encounters import pacing_report
from .keys import solve
from .layout import edge

RULE_REACH = "procgen_reachability"
RULE_PACING = "procgen_pacing"
RULE_LOOT = "procgen_loot"
RULES = (RULE_REACH, RULE_PACING, RULE_LOOT)


def _meta(plan: Mapping[str, Any]) -> Mapping[str, Any] | None:
    m = plan.get("procgen")
    return m if isinstance(m, Mapping) else None


def check_procgen_reachability(plan: Mapping[str, Any]) -> list:
    meta = _meta(plan)
    if meta is None:
        return []
    adj: dict[str, list[str]] = {}
    for lv in items(plan, "levels"):
        if isinstance(lv.get("id"), str):
            adj.setdefault(lv["id"], [])
            for x in lv.get("exits") or []:
                if isinstance(x, str):
                    adj[lv["id"]].append(x)
    # door graph is undirected only where both sides list each other
    und = {k: sorted({n for n in v if k in adj.get(n, [])}) for k, v in adj.items()}
    one_way = sorted(f"{k}->{n}" for k, v in adj.items() for n in v if k not in adj.get(n, []))
    start = plan.get("start_level")
    goals = [g for g in plan.get("goal_levels") or [] if isinstance(g, str)]
    out = []
    if start not in und:
        return [err(RULE_REACH, "start level missing; cannot solve locks")]
    locks = {}
    for row in meta.get("locks") or []:
        if isinstance(row, (list, tuple)) and len(row) == 3:
            a, b, k = row
            if a == b:
                out.append(err(RULE_REACH, f"lock {k!r} is a self edge"))
                continue
            locks[edge(a, b)] = k
            if b not in und.get(a, []):
                out.append(warn(RULE_REACH, f"lock {k!r} sits on missing door {a}-{b}"))
    keys = {k: v for k, v in (meta.get("keys") or {}).items() if isinstance(v, str)}
    missing = sorted(set(locks.values()) - set(keys))
    for k in missing:
        out.append(err(RULE_REACH, f"lock {k!r} has no key placed"))
    for k, room in sorted(keys.items()):
        if room not in und:
            out.append(err(RULE_REACH, f"key {k!r} placed in unknown level {room!r}"))
    for g in goals:
        sol = solve(und, start, g, locks, keys)
        if not sol.solvable:
            out.append(err(RULE_REACH, f"goal {g!r} not reachable with keys; stuck on {list(sol.stuck_on)}"))
        else:
            for lv in sol.unreachable:
                out.append(warn(RULE_REACH, f"level {lv!r} unreachable even with all keys"))
    for ow in one_way:
        out.append(warn(RULE_REACH, f"one-way exit {ow}"))
    return out


def damage_curve(plan: Mapping[str, Any]) -> list[float]:
    meta = _meta(plan) or {}
    player = plan.get("player") if isinstance(plan.get("player"), Mapping) else {}
    try:
        hp, dps = float(player["hp"]), float(player["dps"])  # type: ignore[index]
    except (KeyError, TypeError, ValueError):
        return []
    if hp <= 0 or dps <= 0:
        return []
    encs = {e["id"]: e for e in items(plan, "encounters") if isinstance(e.get("id"), str)}
    levels = {lv["id"]: lv for lv in items(plan, "levels") if isinstance(lv.get("id"), str)}
    path = (meta.get("layout") or {}).get("critical_path") or []
    curve = []
    for lid in path:
        lv = levels.get(lid)
        if lv is None:
            continue
        taken = 0.0
        for eid in lv.get("encounters") or []:
            e = encs.get(eid)
            try:
                taken += float(e["enemy_hp"]) / dps * float(e["enemy_dps"])  # type: ignore[index]
            except (KeyError, TypeError, ValueError):
                continue
        curve.append(taken / hp)
    return curve


def check_procgen_pacing(plan: Mapping[str, Any], *, spike: float = 0.45) -> list:
    if _meta(plan) is None:
        return []
    curve = damage_curve(plan)
    if len(curve) < 3:
        return []
    rep = pacing_report(curve, spike=spike)
    path = (_meta(plan) or {}).get("layout", {}).get("critical_path") or []
    out = []
    for i in rep["spikes"]:
        name = path[i] if i < len(path) else str(i)
        out.append(warn(RULE_PACING, f"difficulty spike entering {name!r}: +{curve[i] - curve[i - 1]:.2f} hp share"))
    if rep["flat"]:
        out.append(warn(RULE_PACING, f"difficulty does not rise along the critical path (trend {rep['trend']:.3f})"))
    if curve and max(curve[:-1] or [0]) > curve[-1] + 1e-9:
        out.append(warn(RULE_PACING, "goal room is not the hardest room on the critical path"))
    return out


def check_procgen_loot(plan: Mapping[str, Any]) -> list:
    if _meta(plan) is None:
        return []
    rows = []
    for lv in items(plan, "levels"):
        info = lv.get("procgen")
        if isinstance(info, Mapping) and isinstance(info.get("loot"), Mapping):
            rows.append((float(info["loot"].get("risk", 0)), float(info["loot"].get("value", 0))))
    if len(rows) < 3:
        return []
    lo = [v for r, v in rows if r <= sorted(r for r, _ in rows)[len(rows) // 2]]
    hi = [v for r, v in rows if r > sorted(r for r, _ in rows)[len(rows) // 2]]
    if lo and hi and sum(hi) / len(hi) < sum(lo) / len(lo):
        return [warn(RULE_LOOT, "riskier rooms carry less loot on average than safer ones")]
    return []


def check_procgen(plan: Any) -> list:
    if not isinstance(plan, Mapping):
        return []
    return [*check_procgen_reachability(plan), *check_procgen_pacing(plan), *check_procgen_loot(plan)]


def score_plan_procgen(plan: Any, thresholds: Thresholds = Thresholds()) -> Verdict:
    """Default ``score_plan`` plus procgen rules; procgen errors downgrade accept to repair.

    The numeric score is the default one (procgen rules carry no weight), so
    comparisons with plain ``score_plan`` stay meaningful.
    """
    base = score_plan(plan, thresholds)
    extra = check_procgen(plan)
    verdict = base.verdict
    if verdict == ACCEPT and any(p.severity is Severity.ERROR for p in extra):
        verdict = REPAIR
    by_rule = dict(base.by_rule)
    for rule in RULES:
        mine = [p for p in extra if p.rule == rule]
        by_rule[rule] = 0.0 if any(p.severity is Severity.ERROR for p in mine) else 1.0
    return Verdict(verdict, base.score, tuple(base.problems) + tuple(extra), by_rule)
