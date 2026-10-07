"""Walk-sim — prove the emitted door graph is playable.

Combat TTK is one identity. This is the other: an operator at player
speed, paying the 0.45s door lock from door.gd, fighting occupants at
compiler TTK, collecting a core when extract is late, must reach extract
before collapse. Time is physics: hypot(Δx,Δy) / speed. Failures are
the builder's, not the operator's.

No Godot binary. The graph + pack are the runtime.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

DOOR_LOCK = 0.45  # matches scripts/world/door.gd


@dataclass
class WalkStep:
    t: float
    room: str
    action: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {"t": round(self.t, 4), "room": self.room, "action": self.action, "detail": self.detail}


@dataclass
class WalkReport:
    extracted: bool
    collapsed: bool
    t: float
    hops: int
    fights: int
    cores: int
    path: List[str]
    required_cores: int
    bound: float = 0.0
    mode: str = "ideal"
    heat_peak: float = 0.0
    vents: int = 0
    steps: List[WalkStep] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if self.extracted and self.t + 1e-6 < self.bound:
            return False
        return self.extracted and not self.collapsed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extracted": self.extracted,
            "collapsed": self.collapsed,
            "passed": self.passed,
            "t": round(self.t, 4),
            "bound": round(self.bound, 4),
            "mode": self.mode,
            "heat_peak": round(self.heat_peak, 3),
            "vents": self.vents,
            "hops": self.hops,
            "fights": self.fights,
            "cores": self.cores,
            "required_cores": self.required_cores,
            "path": list(self.path),
            "notes": list(self.notes),
            "steps": [s.to_dict() for s in self.steps[-24:]],
        }


def _speed(pack: Dict[str, Any]) -> float:
    player = pack.get("player") if isinstance(pack.get("player"), dict) else None
    if player is None or "speed" not in player:
        raise ValueError("player speed is required")
    return _positive(player["speed"], "player speed")


def _positive(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive number")
    number = float(value)
    if not number > 0 or number != number or number == float("inf"):
        raise ValueError(f"{label} must be a positive number")
    return number


def _flag(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _ttk(pack: Dict[str, Any], tier: str) -> float:
    enemies = pack.get("enemies") or []
    for enemy in enemies:
        if isinstance(enemy, dict) and enemy.get("id") == tier and "ttk_target" in enemy:
            return _positive(enemy.get("ttk_target"), "ttk_target")
    ttk = pack.get("ttk") if isinstance(pack.get("ttk"), dict) else {}
    if tier not in ttk:
        raise ValueError(f"missing ttk for {tier}")
    return _positive(ttk[tier], "ttk")


def _enemy(pack: Dict[str, Any], tier: str) -> Optional[Dict[str, Any]]:
    for e in pack.get("enemies") or []:
        if e.get("id") == tier:
            return e
    return None


def _nonneg(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a non-negative number")
    number = float(value)
    if number < 0 or number != number or number == float("inf"):
        raise ValueError(f"{label} must be a non-negative number")
    return number


def _heat_cfg(pack: Dict[str, Any]) -> Dict[str, float]:
    heat = pack.get("heat") if isinstance(pack.get("heat"), dict) else None
    if heat is None:
        raise ValueError("heat is required")
    return {
        "max": _positive(heat.get("max_heat"), "max_heat"),
        "cool": _nonneg(heat.get("passive_cool"), "passive_cool"),
        "sprint": _nonneg(heat.get("sprint_heat_per_sec"), "sprint_heat_per_sec"),
    }


def _tick_heat(heat: float, dt: float, pack: Dict[str, Any], *, sprint: bool = False) -> float:
    cfg = _heat_cfg(pack)
    delta = cfg["sprint"] * dt if sprint else 0.0
    heat = heat + delta - cfg["cool"] * dt
    return max(0.0, min(cfg["max"] * 1.15, heat))


def _adj(graph: Dict[str, Any], pack: Dict[str, Any]) -> Dict[str, List[Tuple[str, float]]]:
    by = {r["id"]: r for r in graph["rooms"]}
    speed = _speed(pack)
    adj: Dict[str, List[Tuple[str, float]]] = {rid: [] for rid in by}
    for d in graph.get("doors") or []:
        a, b = d["from"], d["to"]
        if a not in by or b not in by:
            raise ValueError("door references an unknown room")
        dx = float(by[b]["x"]) - float(by[a]["x"])
        dy = float(by[b]["y"]) - float(by[a]["y"])
        travel = math.hypot(dx, dy) / speed
        adj[a].append((b, max(travel, 0.05) + DOOR_LOCK))
    return adj


def _shortest(adj: Dict[str, List[Tuple[str, float]]], start: str, goal: str,
              forbidden: Optional[set] = None) -> Optional[List[str]]:
    forbidden = forbidden or set()
    if start == goal:
        return [start]
    inf = 1e18
    dist = {start: 0.0}
    prev: Dict[str, str] = {}
    seen: set = set()
    queue = [(0.0, start)]
    while queue:
        queue.sort(key=lambda x: x[0])
        d, u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        if u == goal:
            break
        for v, w in adj.get(u) or []:
            if v in forbidden and v != goal:
                continue
            nd = d + w
            if nd < dist.get(v, inf):
                dist[v] = nd
                prev[v] = u
                queue.append((nd, v))
    if goal not in prev and start != goal:
        return None
    path = [goal]
    while path[-1] != start:
        if path[-1] not in prev:
            return None
        path.append(prev[path[-1]])
    path.reverse()
    return path


def _kind_of(rooms: Dict[str, Dict[str, Any]], rid: str) -> str:
    return str((rooms.get(rid) or {}).get("kind") or "combat")


def _resolve_room(
    pack: Dict[str, Any],
    room: Dict[str, Any],
    *,
    t: float,
    cores: int,
    fights: int,
    steps: List[WalkStep],
    collapse: float,
    heat: float,
    vents: int,
    mode: str,
) -> Tuple[float, int, int, bool, float, int]:
    """Apply occupants. Returns (t, cores, fights, collapsed, heat, vents)."""
    rid = room["id"]
    kind = room.get("kind")
    steps.append(WalkStep(t, rid, "enter", kind or ""))
    if kind == "loot":
        cores += 1
        steps.append(WalkStep(t, rid, "loot", f"cores={cores}"))
        return t, cores, fights, t >= collapse, heat, vents
    if kind == "heat":
        speed = _speed(pack)
        dwell = 180.0 / speed
        t += dwell
        if mode == "thermal":
            heat = _tick_heat(heat, dwell, pack, sprint=True)
        steps.append(WalkStep(t, rid, "heat", f"dwell={dwell:.3f} heat={heat:.1f}"))
        return t, cores, fights, t >= collapse, heat, vents
    if kind == "combat":
        for occ in room.get("occupants") or []:
            if occ.get("kind") != "enemy":
                continue
            tier = str(occ.get("tier") or "trash")
            enemy = _enemy(pack, tier)
            if mode == "thermal" and enemy is not None:
                from skeleton.forge.sim import simulate_encounter
                remaining = max(0.05, collapse - t)
                result = simulate_encounter(
                    pack, enemy, mode="thermal", heat0=heat, max_t=remaining,
                )
                cost = float(result.measured_ttk)
                heat = float(result.heat_end)
                vents += int(result.vents)
                t += cost
                fights += 1
                if tier in {"elite", "boss"}:
                    cores += 1
                steps.append(WalkStep(
                    t, rid, "fight",
                    f"{tier} thermal={cost:.3f} heat={heat:.1f} vents={result.vents}",
                ))
                if result.collapsed or not result.killed or t >= collapse:
                    return t, cores, fights, True, heat, vents
            else:
                cost = _ttk(pack, tier)
                t += cost
                fights += 1
                if tier in {"elite", "boss"}:
                    cores += 1
                steps.append(WalkStep(t, rid, "fight", f"{tier} ttk={cost:.3f}"))
                if t >= collapse:
                    return t, cores, fights, True, heat, vents
        cores += 1
        return t, cores, fights, t >= collapse, heat, vents
    return t, cores, fights, t >= collapse, heat, vents


def walk_graph(
    pack: Dict[str, Any],
    graph: Dict[str, Any],
    *,
    plan: Optional[Dict[str, Any]] = None,
    mode: str = "ideal",
) -> WalkReport:
    plan = plan or {}
    rooms = {r["id"]: r for r in graph["rooms"]}
    spawn = next(r["id"] for r in graph["rooms"] if r["kind"] == "spawn")
    extract = next(r["id"] for r in graph["rooms"] if r["kind"] == "extract")
    adj = _adj(graph, pack)
    session = pack.get("session") if isinstance(pack.get("session"), dict) else {}
    if "collapse_max" not in session:
        raise ValueError("collapse_max is required")
    collapse = _positive(session.get("collapse_max"), "collapse_max")
    if "extract_late" in plan:
        extract_late = _flag(plan.get("extract_late"), "extract_late")
    elif "extract_late" in graph:
        extract_late = _flag(graph.get("extract_late"), "extract_late")
    else:
        extract_late = False
    core_sources = [r["id"] for r in graph["rooms"] if r["kind"] in {"loot", "combat"}]
    required = 1 if (extract_late and core_sources) else 0

    notes: List[str] = []
    steps: List[WalkStep] = []
    path: List[str] = [spawn]
    t = 0.0
    hops = 0
    fights = 0
    cores = 0
    vents = 0
    heat = 0.0
    heat_peak = 0.0
    current = spawn
    collapsed = False
    extracted = False

    t, cores, fights, collapsed, heat, vents = _resolve_room(
        pack, rooms[spawn], t=t, cores=cores, fights=fights, steps=steps,
        collapse=collapse, heat=heat, vents=vents, mode=mode,
    )
    heat_peak = max(heat_peak, heat)

    def target() -> Optional[str]:
        if cores < required:
            # nearest core source not yet visited as last hop
            best = None
            best_len = 10**9
            for src in core_sources:
                if src == current:
                    return src
                p = _shortest(adj, current, src, forbidden={extract} if required else None)
                if p and len(p) < best_len:
                    best, best_len = src, len(p)
            return best or extract
        return extract

    seen_goals = 0
    while not extracted and not collapsed and seen_goals < len(rooms) * 4:
        goal = target()
        if goal is None:
            notes.append("no core source and extract locked")
            break
        forbidden = {extract} if (cores < required and goal != extract) else set()
        route = _shortest(adj, current, goal, forbidden=forbidden)
        if route is None:
            # locked extract: try without forbidding
            route = _shortest(adj, current, goal, forbidden=set())
        if route is None:
            notes.append(f"no door path {current} → {goal}")
            break
        if len(route) == 1:
            if current == extract and cores >= required:
                extracted = True
                steps.append(WalkStep(t, current, "extract", f"cores={cores}"))
                break
            if current == extract and cores < required:
                notes.append("extract locked; zero cores")
                break
            # already at a core source; occupancy already resolved
            if cores >= required:
                goal = extract
                seen_goals += 1
                continue
            notes.append("stuck at core source with no door out")
            break
        nxt = route[1]
        # travel along the matching door
        travel = next((w for v, w in adj[current] if v == nxt), 0.5)
        if cores < required and nxt == extract:
            notes.append("door to extract locked until a core")
            # pick another neighbour
            alt = [v for v, _ in adj[current] if v != extract]
            if not alt:
                break
            nxt = alt[0]
            travel = next((w for v, w in adj[current] if v == nxt), 0.5)
        t += travel
        if mode == "thermal":
            heat = _tick_heat(heat, travel, pack, sprint=False)
        hops += 1
        current = nxt
        path.append(current)
        t, cores, fights, collapsed, heat, vents = _resolve_room(
            pack, rooms[current], t=t, cores=cores, fights=fights, steps=steps,
            collapse=collapse, heat=heat, vents=vents, mode=mode,
        )
        heat_peak = max(heat_peak, heat)
        if collapsed:
            notes.append(f"collapse at t={t:.2f}s in {current}")
            break
        if current == extract and cores >= required:
            extracted = True
            steps.append(WalkStep(t, current, "extract", f"cores={cores}"))
            break
        seen_goals += 1

    if extracted:
        notes.append(f"extracted t={t:.2f}s hops={hops} cores={cores}/{required}")
    elif not notes:
        notes.append("walk exhausted without extract")

    bound = 0.0
    shortest = _shortest(adj, spawn, extract)
    if shortest and len(shortest) > 1:
        for a, b in zip(shortest, shortest[1:]):
            bound += next((w for v, w in adj[a] if v == b), 0.0)
    if extracted and t + 1e-6 < bound:
        notes.append(f"teleport: t={t:.4f} < bound={bound:.4f}")

    return WalkReport(
        extracted=extracted,
        collapsed=collapsed,
        t=t,
        hops=hops,
        fights=fights,
        cores=cores,
        path=path,
        required_cores=required,
        bound=bound,
        mode=mode,
        heat_peak=heat_peak,
        vents=vents,
        steps=steps,
        notes=notes,
    )


def walk_from_pack(
    pack: Dict[str, Any],
    *,
    plan: Optional[Dict[str, Any]] = None,
    mode: str = "ideal",
) -> WalkReport:
    from skeleton.forge.world import generate_rooms
    graph = generate_rooms(pack, seed=str((plan or {}).get("seed") or pack.get("era")), plan=plan)
    return walk_graph(pack, graph, plan=plan, mode=mode)
