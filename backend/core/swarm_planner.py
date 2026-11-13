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
import json
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
    if not isinstance(build_id, str) or not 1 <= len(build_id.strip()) <= 128:
        raise ValueError("build_id must be a bounded non-empty string")
    # None selects canonical defaults; an explicitly empty request must never
    # manufacture 100 phases or invent a sequential dependency chain.
    if phases is None:
        phases = list(DEFAULT_PHASES)
    elif not isinstance(phases, (list, tuple)):
        raise ValueError("phases must be a list of phase identifiers")
    else:
        phases = list(phases)
    if not phases:
        raise ValueError("at least one phase is required")
    if len(phases) > MAX_PHASES:
        raise ValueError(f"too many phases (max {MAX_PHASES})")
    if any(
        not isinstance(phase, str)
        or not 1 <= len(phase.strip()) <= 128
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in phase)
        for phase in phases
    ):
        raise ValueError("phase ids must be bounded non-empty strings")
    if len(set(phases)) != len(phases):
        raise ValueError("duplicate phase ids are not allowed")
    if type(platoon_size) is not int or platoon_size < 1:
        raise ValueError("platoon_size must be a positive integer")
    platoon_size = max(MIN_PLATOON, min(MAX_PLATOON, platoon_size))
    if type(seed) is not int or not -(2 ** 63) <= seed < 2 ** 63:
        raise ValueError("seed must be a signed 64-bit integer")
    if game_ctx is None:
        game_ctx = {}
    if not isinstance(game_ctx, dict):
        raise ValueError("game context must be an object")
    genre = game_ctx.get("genre", "")
    if not isinstance(genre, str) or len(genre) > 256:
        raise ValueError("game context genre must be bounded text")
    if objectives is None:
        objectives = ["ship a complete, polished, original game"]
    elif not isinstance(objectives, (list, tuple)):
        raise ValueError("objectives must be a list of text")
    else:
        objectives = list(objectives)
    if not 1 <= len(objectives) <= 100 or any(
        not isinstance(obj, str) or not 1 <= len(obj.strip()) <= 512 for obj in objectives
    ):
        raise ValueError("objectives must contain bounded non-empty text")

    if deps is None:
        deps = _default_chain_deps(phases)
    elif not isinstance(deps, dict):
        raise ValueError("dependencies must be a phase-to-list mapping")
    else:
        if any(not isinstance(key, str) for key in deps):
            raise ValueError("dependency keys must be phase identifiers")
        unknown = set(deps) - set(phases)
        if unknown:
            raise ValueError(f"dependencies name unknown phases: {sorted(unknown)[:5]}")
        for phase, required in deps.items():
            if (not isinstance(required, (list, tuple)) or len(required) > len(phases)) or any(
                not isinstance(dep, str) for dep in required
            ):
                raise ValueError(f"invalid dependency list for phase {phase}")
            if len(set(required)) != len(required):
                raise ValueError(f"duplicate dependencies for phase {phase}")
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
        "genre": genre,
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
    """Versioned, unambiguous identity for a fully specified build plan.

    Former hashes covered only worker codes, DAG edges and seed. Distinct
    builds or changed objectives could therefore share the same receipt ID.
    """
    basis = {
        "schema": "swarm-plan-v2",
        "build_id": plan["build_id"],
        "seed": plan["seed"],
        "platoon_size": plan["platoon_size"],
        "genre": plan["genre"],
        "objectives": plan["objectives"],
        "phases": [
            {"id": node["phase_id"], "workers": [worker["code"] for worker in node["workers"]]}
            for node in plan["nodes"] if node["tier"] == "platoon"
        ],
        "edges": plan["edges"],
    }
    encoded = json.dumps(
        basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def verify_plan(plan: dict) -> dict:
    """Independently re-validate a plan: acyclic, fully reachable, 100% covered."""
    nodes = {n["id"]: n for n in plan.get("nodes", [])}
    edges = plan.get("edges", [])
    problems: list[str] = []
    if len(nodes) != len(plan.get("nodes", [])):
        problems.append("duplicate node identities")
    for edge in edges:
        if edge.get("from") not in nodes or edge.get("to") not in nodes:
            problems.append("edge references an unknown node")

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

    # 3) Independently recompute expected phases from the plan's declared
    # execution waves. Never trust a mutable coverage summary as proof.
    expected_phases = [
        phase for wave in plan.get("waves", []) for phase in wave.get("phases", [])
    ]
    expected_set = set(expected_phases)
    actual_set = set(phase_nodes)
    unique = (
        bool(expected_phases)
        and len(expected_phases) == len(expected_set)
        and len(phase_nodes) == len(actual_set)
        and len(expected_phases) == plan.get("phase_count")
        and len(phase_nodes) == len(expected_phases)
        and actual_set == expected_set
    )
    computed = _coverage(plan, expected_phases)
    provided = plan.get("coverage", {})
    coverage_ok = unique and computed["all_covered"] and provided == computed
    if not coverage_ok:
        problems.append("coverage incomplete or stale versus actual nodes")

    # 4) A platoon with missing/duplicated worker identities is not complete.
    for n in plan.get("nodes", []):
        if n["tier"] != "platoon":
            continue
        worker_codes = [worker.get("code") for worker in n.get("workers", [])]
        if (
            n.get("size", 0) < 1
            or n.get("size") != len(worker_codes)
            or any(not isinstance(code, str) or not code for code in worker_codes)
            or len(set(worker_codes)) != len(worker_codes)
        ):
            problems.append(f"platoon {n['id']} has invalid worker custody")

    # 5) Rebuild the receipt from current plan contents. Changed objectives,
    # participants, source identity or edges invalidate historical attestations.
    try:
        receipt_ok = plan.get("plan_hash") == _plan_hash(plan)
    except (KeyError, TypeError, ValueError):
        receipt_ok = False
    if not receipt_ok:
        problems.append("plan source receipt does not match current contents")

    return {
        "valid": not problems,
        "acyclic": acyclic,
        "fully_reachable": not unreachable,
        "coverage_ok": coverage_ok,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "problems": problems,
    }
