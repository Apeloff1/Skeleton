"""
╔════════════════════════════════════════════════════════════════════════╗
║  HIERARCHICAL SWARM PLANNER  (Backlog I.3)                              ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Turns a build (a set of phases + objectives) into a 4-tier task DAG:   ║
║                                                                        ║
║      DIRECTOR ── owns the whole build                                  ║
║         │                                                              ║
║         ├── LEAD (one per legion) ── owns a slice of phases            ║
║         │       │                                                      ║
║         │       └── PLATOON (one per phase) ── microteam               ║
║         │               │                                              ║
║         │               └── WORKER (agent) ── leaf executor            ║
║                                                                        ║
║  Guarantees:                                                           ║
║    • PROVABLE 100% COVERAGE — every phase is owned by exactly one      ║
║      platoon + lead, and every platoon has ≥1 worker.                  ║
║    • DEPENDENCY ORDERING — phases topologically sorted into parallel   ║
║      "waves" (Kahn's algorithm); cycles are rejected.                  ║
║    • DETERMINISTIC SEEDS — identical (seed, phases, deps) ⇒ identical  ║
║      plan, so a build is perfectly reproducible.                       ║
║                                                                        ║
║  Pure / in-memory / no LLM — fast and unit-testable.                   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

from core.swarm_agents import SWARM_DOMAINS, BY_LEGION, BY_CATEGORY

# Canonical 100-phase taxonomy (p01..p100) used by Galaxy Studio builds.
DEFAULT_PHASES: list[str] = [f"p{i:02d}" for i in range(1, 101)]

MAX_PHASES = 500
MIN_PLATOON = 2
MAX_PLATOON = 12


# ── deterministic helpers ────────────────────────────────────────────────
def _rng(*parts: Any) -> random.Random:
    """A reproducible RNG keyed on a stable string of the given parts."""
    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _legions() -> list[str]:
    return sorted(BY_LEGION.keys())


# ── topological waves (Kahn) ─────────────────────────────────────────────
def topo_waves(phases: list[str], deps: dict[str, list[str]]) -> list[list[str]]:
    """Group phases into parallel execution waves respecting dependencies.

    Raises ValueError on an unknown dependency or a cycle.
    """
    phase_set = set(phases)
    indeg: dict[str, int] = {p: 0 for p in phases}
    adj: dict[str, list[str]] = {p: [] for p in phases}
    for p in phases:
        for d in deps.get(p, []):
            if d not in phase_set:
                raise ValueError(f"phase '{p}' depends on unknown phase '{d}'")
            if d == p:
                raise ValueError(f"phase '{p}' cannot depend on itself")
            adj[d].append(p)
            indeg[p] += 1

    waves: list[list[str]] = []
    # Preserve input order inside a wave for stable, readable output.
    frontier = [p for p in phases if indeg[p] == 0]
    seen = 0
    while frontier:
        waves.append(list(frontier))
        seen += len(frontier)
        nxt: list[str] = []
        for p in frontier:
            for child in adj[p]:
                indeg[child] -= 1
                if indeg[child] == 0:
                    nxt.append(child)
        # keep input ordering deterministic within the next wave
        nxt.sort(key=lambda x: phases.index(x))
        frontier = nxt

    if seen != len(phases):
        raise ValueError("dependency cycle detected — DAG is not acyclic")
    return waves


def _default_chain_deps(phases: list[str]) -> dict[str, list[str]]:
    """Sequential fallback: phase i depends on phase i-1."""
    return {phases[i]: [phases[i - 1]] for i in range(1, len(phases))}


# ── the planner ──────────────────────────────────────────────────────────
def plan_build(
    build_id: str,
    phases: list[str] | None = None,
    objectives: list[str] | None = None,
    deps: dict[str, list[str]] | None = None,
    seed: int = 0,
    platoon_size: int = 5,
    game_ctx: dict[str, Any] | None = None,
) -> dict:
    """Produce the hierarchical task DAG for a build.

    Returns a JSON-serialisable plan with director/leads/platoons/workers,
    dependency edges, topological waves and a coverage proof.
    """
    phases = list(phases or DEFAULT_PHASES)
    if not phases:
        raise ValueError("at least one phase is required")
    if len(phases) > MAX_PHASES:
        raise ValueError(f"too many phases (max {MAX_PHASES})")
    if len(set(phases)) != len(phases):
        raise ValueError("duplicate phase ids are not allowed")
    platoon_size = max(MIN_PLATOON, min(MAX_PLATOON, platoon_size))
    game_ctx = game_ctx or {}
    objectives = objectives or ["ship a complete, polished, original game"]

    deps = deps or _default_chain_deps(phases)
    waves = topo_waves(phases, deps)
    depth_of: dict[str, int] = {}
    for w_idx, wave in enumerate(waves):
        for p in wave:
            depth_of[p] = w_idx

    legions = _legions()
    n_leads = len(legions)

    nodes: list[dict] = []
    edges: list[dict] = []

    # ── DIRECTOR ──────────────────────────────────────────────────────
    director_id = "director"
    nodes.append({
        "id": director_id,
        "tier": "director",
        "title": "Build Director",
        "owns": "whole-build",
        "objectives": objectives,
        "phase_count": len(phases),
    })

    # ── LEADS (one per legion) ────────────────────────────────────────
    # Deterministically assign each phase to a lead (round-robin by index so
    # the spread is balanced and reproducible).
    lead_ids: list[str] = []
    lead_phases: dict[str, list[str]] = {}
    for i, legion_id in enumerate(legions):
        lead_id = f"lead::{legion_id}"
        lead_ids.append(lead_id)
        lead_phases[lead_id] = []
        members = BY_LEGION[legion_id]
        head = members[0] if members else {}
        nodes.append({
            "id": lead_id,
            "tier": "lead",
            "title": head.get("legion_name", legion_id),
            "legion_id": legion_id,
            "lead_agent": head.get("agent"),
            "lead_agent_code": head.get("agent_code"),
            "objective": objectives[i % len(objectives)],
        })
        edges.append({"from": director_id, "to": lead_id, "kind": "delegates"})

    for idx, phase in enumerate(phases):
        owner = lead_ids[idx % n_leads]
        lead_phases[owner].append(phase)

    # ── PLATOONS (one per phase) + WORKERS ────────────────────────────
    worker_assignments: dict[str, list[str]] = {}   # phase -> [agent_code]
    agent_seat_count: dict[str, int] = {}
    pool = SWARM_DOMAINS
    n_pool = len(pool)

    for idx, phase in enumerate(phases):
        owner_lead = lead_ids[idx % n_leads]
        platoon_id = f"platoon::{phase}"
        rng = _rng("platoon", seed, phase, game_ctx.get("genre", ""))

        # Deterministic balanced worker pick: stride across the pool from a
        # phase-derived offset, then jitter with the seeded RNG.
        start = (idx * platoon_size + rng.randint(0, max(0, n_pool - 1))) % max(1, n_pool)
        chosen: list[dict] = []
        seen_ids: set[str] = set()
        step = max(1, n_pool // platoon_size)
        k = 0
        while len(chosen) < min(platoon_size, n_pool) and k < n_pool * 2:
            a = pool[(start + k * step) % n_pool]
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                chosen.append(a)
            k += 1

        worker_codes = [a.get("agent_code") or a["id"] for a in chosen]
        worker_assignments[phase] = worker_codes
        for code in worker_codes:
            agent_seat_count[code] = agent_seat_count.get(code, 0) + 1

        nodes.append({
            "id": platoon_id,
            "tier": "platoon",
            "title": f"Platoon · {phase}",
            "phase_id": phase,
            "lead_id": owner_lead,
            "wave": depth_of[phase],
            "size": len(chosen),
            "workers": [
                {
                    "code": a.get("agent_code") or a["id"],
                    "agent": a.get("agent"),
                    "category": a.get("category"),
                }
                for a in chosen
            ],
        })
        edges.append({"from": owner_lead, "to": platoon_id, "kind": "owns"})

        # phase-dependency edges between platoons (the DAG ordering)
        for d in deps.get(phase, []):
            edges.append({"from": f"platoon::{d}", "to": platoon_id, "kind": "depends-on"})

    plan = {
        "build_id": build_id,
        "seed": seed,
        "platoon_size": platoon_size,
        "phase_count": len(phases),
        "lead_count": n_leads,
        "objectives": objectives,
        "tiers": ["director", "lead", "platoon", "worker"],
        "nodes": nodes,
        "edges": edges,
        "waves": [{"wave": i, "phases": w} for i, w in enumerate(waves)],
        "critical_path_len": len(waves),
        "lead_load": {lid: len(ph) for lid, ph in lead_phases.items()},
        "worker_assignments": worker_assignments,
        "distinct_workers": len(agent_seat_count),
        "max_worker_load": max(agent_seat_count.values()) if agent_seat_count else 0,
    }
    plan["coverage"] = _coverage(plan, phases)
    plan["plan_hash"] = _plan_hash(plan)
    return plan


def _coverage(plan: dict, phases: list[str]) -> dict:
    covered = set()
    empty_platoons = []
    for node in plan["nodes"]:
        if node["tier"] == "platoon":
            covered.add(node["phase_id"])
            if node["size"] < 1:
                empty_platoons.append(node["phase_id"])
    missing = [p for p in phases if p not in covered]
    total = len(phases)
    return {
        "phases_total": total,
        "phases_covered": len(covered),
        "coverage_pct": round(len(covered) / max(total, 1) * 100, 2),
        "all_covered": len(missing) == 0 and not empty_platoons,
        "missing_phases": missing,
        "empty_platoons": empty_platoons,
    }


def _plan_hash(plan: dict) -> str:
    basis = "|".join(
        f"{n['id']}:{','.join(w['code'] for w in n.get('workers', []))}"
        for n in plan["nodes"] if n["tier"] == "platoon"
    )
    basis += "||" + "|".join(f"{e['from']}->{e['to']}" for e in plan["edges"])
    return hashlib.sha256(f"{plan['seed']}::{basis}".encode()).hexdigest()[:16]


def verify_plan(plan: dict) -> dict:
    """Independently re-validate a plan: acyclic, fully reachable, 100% covered."""
    nodes = {n["id"]: n for n in plan.get("nodes", [])}
    edges = plan.get("edges", [])
    problems: list[str] = []

    # 1) acyclicity over the platoon dependency sub-graph
    phase_nodes = [n["phase_id"] for n in plan.get("nodes", []) if n["tier"] == "platoon"]
    deps: dict[str, list[str]] = {p: [] for p in phase_nodes}
    for e in edges:
        if e["kind"] == "depends-on":
            frm = e["from"].replace("platoon::", "")
            to = e["to"].replace("platoon::", "")
            if to in deps:
                deps[to].append(frm)
    acyclic = True
    try:
        topo_waves(phase_nodes, deps)
    except ValueError as ex:
        acyclic = False
        problems.append(f"dependency graph invalid: {ex}")

    # 2) reachability — every node reachable from the director
    reachable: set[str] = set()
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e["from"], []).append(e["to"])
    stack = ["director"]
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        stack.extend(adj.get(cur, []))
    unreachable = [nid for nid in nodes if nid not in reachable]
    if unreachable:
        problems.append(f"{len(unreachable)} unreachable node(s) from director")

    # 3) coverage
    cov = plan.get("coverage", {})
    if not cov.get("all_covered"):
        problems.append("coverage incomplete")

    # 4) every platoon has ≥1 worker
    for n in plan.get("nodes", []):
        if n["tier"] == "platoon" and n.get("size", 0) < 1:
            problems.append(f"platoon {n['id']} has no workers")

    return {
        "valid": not problems,
        "acyclic": acyclic,
        "fully_reachable": not unreachable,
        "coverage_ok": bool(cov.get("all_covered")),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "problems": problems,
    }
