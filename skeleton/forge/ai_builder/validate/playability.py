"""Reachability, encounter feasibility (the plan's own stats), logic-loop detection.

Feasibility is a sanity bound on the plan's own numbers - time-to-kill vs.
damage taken - not economy balance.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from ._common import err, items, warn


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def exit_graph(plan: Mapping[str, Any]) -> dict[str, list[str]]:
    """Directed level graph from ``levels[].exits`` (exits to unknown levels dropped).

    Shared by validate and procgen so both read exits the same way.
    """
    graph = {lv["id"]: [x for x in lv.get("exits") or [] if isinstance(x, str)]
             for lv in items(plan, "levels") if isinstance(lv.get("id"), str)}
    return {k: sorted({n for n in v if n in graph}) for k, v in graph.items()}


def one_way_exits(graph: Mapping[str, list[str]]) -> list[tuple[str, str]]:
    """The one shared one-way-exit rule: ``a -> b`` is one-way when ``b`` does not list ``a``.

    One-way exits are legal (drops, slides); they are only a problem when they
    lead into a softlock, which both validate and procgen report via
    :func:`dead_end_states` / ``procgen.keys.softlocks``.
    """
    return sorted((a, b) for a, outs in graph.items() for b in outs if a not in graph.get(b, ()))


def dead_end_states(graph: Mapping[str, list[str]], start: str, goals: list[str]) -> list[str]:
    """Levels reachable from ``start`` (keyless) from which no goal is reachable."""
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in graph.get(queue.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    rev: dict[str, list[str]] = {k: [] for k in graph}
    for a, outs in graph.items():
        for b in outs:
            rev[b].append(a)
    good = {g for g in goals if g in seen}
    stack = list(good)
    while stack:
        for p in rev.get(stack.pop(), ()):
            if p in seen and p not in good:
                good.add(p)
                stack.append(p)
    return sorted(seen - good) if good else []


def check_reachability(plan: Mapping[str, Any]) -> list:
    rule = "reachability"
    graph = exit_graph(plan)
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
    ow = one_way_exits(graph)
    if ow:
        stuck = set(dead_end_states(graph, start, goals))
        for a, b in ow:
            if b in stuck:
                out.append(warn(rule, f"one-way exit {a}->{b} leads to a softlock"))
    return out


def check_winnable(plan: Mapping[str, Any], *, margin: float = 1.0) -> list:
    """A level is winnable if the player survives all of its encounters back to
    back on one health pool: sum(enemy_hp / player.dps * enemy_dps) < hp / margin."""
    rule = "winnable"
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
    by_event: dict[str, list[Mapping[str, Any]]] = {}
    for t in trig:
        by_event.setdefault(t["on"], []).append(t)
    # trigger -> triggers it can fire
    edges = {t["id"]: [n["id"] for ev in t.get("emits") or [] for n in by_event.get(ev, [])] for t in trig}
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
