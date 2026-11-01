"""Reachability, encounter feasibility (the plan's own stats), logic-loop detection.

Feasibility is a sanity bound on the plan's own numbers - time-to-kill vs.
damage taken - not economy balance.
"""
from __future__ import annotations

from collections import deque
import math
from typing import Any, Mapping

from ._common import err, items, warn


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        n = float(v)
    except (OverflowError, TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def check_reachability(plan: Mapping[str, Any]) -> list:
    rule = "reachability"
    graph = {lv["id"]: [x for x in lv.get("exits") or [] if isinstance(x, str)]
             for lv in items(plan, "levels") if isinstance(lv.get("id"), str)}
    start = plan.get("start_level")
    if start not in graph:
        return [err(rule, "no start level to search from")]
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in graph[queue.popleft()]:
            if nxt in graph and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    goals = [g for g in plan.get("goal_levels") or [] if isinstance(g, str)]
    out = []
    if goals and not any(g in seen for g in goals):
        out.append(err(rule, "no goal level is reachable from start"))
    for g in goals:
        if g in graph and g not in seen:
            out.append(warn(rule, f"goal {g!r} unreachable"))
    for lv in sorted(set(graph) - seen - set(goals)):
        out.append(warn(rule, f"level {lv!r} unreachable"))
    return out


def check_winnable(plan: Mapping[str, Any], *, margin: float = 1.0) -> list:
    """A level is winnable if the player survives all of its encounters back to
    back on one health pool: sum(enemy_hp / player.dps * enemy_dps) < hp / margin."""
    rule = "winnable"
    margin_value = _num(margin)
    if margin_value is None or margin_value <= 0:
        return [err(rule, "margin must be finite and strictly positive")]
    margin = margin_value
    player = plan.get("player") if isinstance(plan.get("player"), Mapping) else {}
    hp, dps = _num(player.get("hp")), _num(player.get("dps"))
    if not hp or not dps or hp <= 0 or dps <= 0:
        return [err(rule, "player stats missing; cannot prove winnability")]
    encs = {e["id"]: e for e in items(plan, "encounters") if isinstance(e.get("id"), str)}
    out = []
    for eid, e in encs.items():
        ehp, edps = _num(e.get("enemy_hp")), _num(e.get("enemy_dps"))
        if ehp is None or edps is None:
            continue
        if ehp / dps * edps >= hp / margin:
            out.append(err(rule, f"encounter {eid!r} unwinnable: takes {ehp / dps * edps:.1f} dmg vs hp {hp:g}"))
    for lv in items(plan, "levels"):
        taken = 0.0
        for eid in lv.get("encounters") or []:
            e = encs.get(eid)
            if e and _num(e.get("enemy_hp")) is not None and _num(e.get("enemy_dps")) is not None:
                taken += e["enemy_hp"] / dps * e["enemy_dps"]
        if taken >= hp / margin and len(lv.get("encounters") or []) > 1:
            out.append(err(rule, f"level {lv.get('id')!r} unwinnable in sequence: {taken:.1f} dmg vs hp {hp:g}"))
        elif taken >= 0.8 * hp / margin:
            out.append(warn(rule, f"level {lv.get('id')!r} near-lethal: {taken:.1f} dmg vs hp {hp:g}"))
    return out


def check_cycles(plan: Mapping[str, Any]) -> list:
    """Trigger graph: event --(trigger.on)--> trigger --(emits)--> event.

    A cycle is an infinite logic loop unless some trigger on it is ``once``.
    Iterative DFS (no recursion limit)."""
    rule = "logic_loop"
    trig = [t for t in items(plan, "triggers") if isinstance(t.get("id"), str) and isinstance(t.get("on"), str)]
    if len(trig) > 8192:
        return [err(rule, "trigger node budget exceeded")]
    by_event: dict[str, list[Mapping[str, Any]]] = {}
    for t in trig:
        by_event.setdefault(t["on"], []).append(t)
    # trigger -> triggers it can fire
    edges: dict[str, list[str]] = {}
    edge_count = 0
    for t in trig:
        emits = t.get("emits") or []
        if not isinstance(emits, list) or len(emits) > 256 or any(not isinstance(x, str) for x in emits):
            return [err(rule, "malformed trigger emissions")]
        links: list[str] = []
        for ev in emits:
            next_links = by_event.get(ev, [])
            if len(next_links) > 50_000 - edge_count - len(links):
                return [err(rule, "trigger edge budget exceeded")]
            links.extend(x["id"] for x in next_links)
        edge_count += len(links)
        edges[t["id"]] = links
    once = {t["id"] for t in trig if t.get("once") is True}
    out, state, reported = [], {}, set()
    for root in edges:
        if state.get(root):
            continue
        path: list[str] = []
        stack = [(root, iter(edges[root]))]
        state[root] = 1
        path.append(root)
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                stack.pop()
                path.pop()
                state[node] = 2
            elif state.get(nxt) == 1:
                cycle = tuple(path[path.index(nxt):])
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    if once & key:
                        out.append(warn(rule, f"bounded loop {' -> '.join(cycle + (nxt,))} (once)"))
                    else:
                        out.append(err(rule, f"infinite loop {' -> '.join(cycle + (nxt,))}"))
            elif not state.get(nxt):
                state[nxt] = 1
                path.append(nxt)
                stack.append((nxt, iter(edges[nxt])))
    return out
