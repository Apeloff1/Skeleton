"""Validation rules for procgen output.

``validate.score_plan`` runs :func:`check_procgen` on any plan carrying a
``plan["procgen"]`` section (plans without one score exactly as before).
The rules carry no score weight; their errors force ``repair``.
:func:`score_plan_procgen` adds per-rule sub-scores. Rules re-derive everything from the plan itself
(levels, exits, encounters, player), using ``plan["procgen"]`` only for the
lock/key placement, so hand edits after generation are caught.
"""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.forge.ai_builder.validate._common import err, items, warn
from skeleton.forge.ai_builder.validate.playability import exit_graph, one_way_exits
from skeleton.forge.ai_builder.validate.scoring import Thresholds, Verdict, score_plan
from skeleton.forge.validator import Severity

from .encounters import pacing_report
from .keys import gates, key_distances, softlocks, solve
from .layout import edge
from .metrics import LayoutLimits, layout_metrics, metric_violations

RULE_REACH = "procgen_reachability"
RULE_PACING = "procgen_pacing"
RULE_LOOT = "procgen_loot"
RULE_LAYOUT = "procgen_layout"
RULES = (RULE_REACH, RULE_PACING, RULE_LOOT, RULE_LAYOUT)


def _meta(plan: Mapping[str, Any]) -> Mapping[str, Any] | None:
    m = plan.get("procgen")
    return m if isinstance(m, Mapping) else None


def _limits(meta: Mapping[str, Any]) -> LayoutLimits:
    cfg = meta.get("config")
    return LayoutLimits.from_mapping(cfg.get("limits") if isinstance(cfg, Mapping) else None)


def check_procgen_reachability(plan: Mapping[str, Any]) -> list:
    """Lock/key solve on the *directed* exit graph, state (level, keys held), plus softlocks.

    Uses validate's shared exit rule (:func:`exit_graph` / :func:`one_way_exits`):
    one-way exits are legal and solved as directed edges; they are an error
    only when they lead into a softlock.
    """
    meta = _meta(plan)
    if meta is None:
        return []
    adj = exit_graph(plan)
    start = plan.get("start_level")
    goals = [g for g in plan.get("goal_levels") or [] if isinstance(g, str)]
    out = []
    if start not in adj:
        return [err(RULE_REACH, "start level missing; cannot solve locks")]
    locks = {}
    for row in meta.get("locks") or []:
        if isinstance(row, (list, tuple)) and len(row) == 3:
            a, b, k = row
            if a == b:
                out.append(err(RULE_REACH, f"lock {k!r} is a self edge"))
                continue
            locks[edge(a, b)] = k
            if b not in adj.get(a, []) and a not in adj.get(b, []):
                out.append(warn(RULE_REACH, f"lock {k!r} sits on missing door {a}-{b}"))
    keys = {k: v for k, v in (meta.get("keys") or {}).items() if isinstance(v, str)}
    missing = sorted(set(locks.values()) - set(keys))
    for k in missing:
        out.append(err(RULE_REACH, f"lock {k!r} has no key placed"))
    for k, room in sorted(keys.items()):
        if room not in adj:
            out.append(err(RULE_REACH, f"key {k!r} placed in unknown level {room!r}"))
    for g in goals:
        sol = solve(adj, start, g, locks, keys)
        if not sol.solvable:
            out.append(err(RULE_REACH, f"goal {g!r} not reachable with keys; stuck on {list(sol.stuck_on)}"))
        else:
            for lv in sol.unreachable:
                out.append(warn(RULE_REACH, f"level {lv!r} unreachable even with all keys"))
    if goals:
        soft = softlocks(adj, start, goals, locks, keys)
        if soft["goal_reachable"] and soft["softlock_rooms"]:
            ow = [f"{a}->{b}" for a, b in one_way_exits(adj) if b in soft["softlock_rooms"]]
            out.append(err(RULE_REACH, f"softlock: no way to a goal from {soft['softlock_rooms']}"
                                       + (f" (one-way exits {ow})" if ow else "")))
    for k, n in sorted(gates(adj, start, locks).items()):
        if n == 0 and k in keys:
            out.append(err(RULE_REACH, f"lock {k!r} gates 0 levels (walk-around or redundant)"))
    req = meta.get("locks_requested")
    if isinstance(req, int) and req > len(set(locks.values())):
        out.append(warn(RULE_REACH, f"{req} locks requested, {len(set(locks.values()))} placed "
                                    "(not enough lockable gating doors)"))
    limit = _limits(meta).max_key_distance
    for k, d in sorted(key_distances(adj, locks, keys, start).items()):
        if d is not None and d > limit:
            out.append(warn(RULE_REACH, f"key {k!r} is {d} doors from its lock (limit {limit})"))
    return out


def check_procgen_layout(plan: Mapping[str, Any]) -> list:
    meta = _meta(plan)
    if meta is None:
        return []
    adj = exit_graph(plan)
    start, goals = plan.get("start_level"), [g for g in plan.get("goal_levels") or [] if isinstance(g, str)]
    if start not in adj or not goals:
        return []
    path = (meta.get("layout") or {}).get("critical_path") or []
    m = layout_metrics(adj, path, start, goals[0])
    return [warn(RULE_LAYOUT, msg) for msg in metric_violations(m, _limits(meta))]


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


def check_procgen_pacing(plan: Mapping[str, Any], *, spike: float | None = None) -> list:
    """``spike`` defaults to 30% of the plan's per-room cap (see ``encounters.spike_threshold``)."""
    meta = _meta(plan)
    if meta is None:
        return []
    curve = damage_curve(plan)
    if len(curve) < 3:
        return []
    cap = (meta.get("difficulty") or {}).get("cap") if isinstance(meta.get("difficulty"), Mapping) else None
    rep = pacing_report(curve, spike=spike, cap=cap if isinstance(cap, (int, float)) else None)
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
    return [*check_procgen_reachability(plan), *check_procgen_pacing(plan), *check_procgen_loot(plan),
            *check_procgen_layout(plan)]


def score_plan_procgen(plan: Any, thresholds: Thresholds = Thresholds()) -> Verdict:
    """Default ``score_plan`` (which already runs the procgen rules) plus per-rule procgen sub-scores.

    The numeric score is the default one (procgen rules carry no weight), so
    comparisons with plain ``score_plan`` stay meaningful.
    """
    base = score_plan(plan, thresholds)
    by_rule = dict(base.by_rule)
    for rule in RULES:
        mine = [p for p in base.problems if p.rule == rule]
        by_rule[rule] = 0.0 if any(p.severity is Severity.ERROR for p in mine) else 1.0
    return Verdict(base.verdict, base.score, tuple(base.problems), by_rule)
