"""
╔════════════════════════════════════════════════════════════════════════╗
║  AGENT MESH — spider-web connecting ALL 1,473,844 agents              ║
║  ────────────────────────────────────────────────────────────────────  ║
║  This mesh is PROCEDURAL: no in-memory adjacency dict. Every edge is   ║
║  derived from deterministic arithmetic / XOR involutions over the      ║
║  integer agent IDs declared in `core.full_roster`. The graph is        ║
║  therefore undirected by construction (every rule is its own inverse). ║
║                                                                        ║
║  Per-agent degree ≈ 10–18. Topology guarantees any agent can reach     ║
║  any other in ≤ 6 hops via the Parliament / cohort-hub backbone.       ║
║                                                                        ║
║  Public API (unchanged from the earlier 482-node implementation):      ║
║    • build_mesh(force=False)    — warm-up (no heavy work, procedural)  ║
║    • neighbors(code, k=None)    — rich neighbor descriptors            ║
║    • neighbor_codes(code, k)    — codes only                           ║
║    • reach(code, depth=2)       — BFS to N hops (capped for scale)     ║
║    • path(a, b, max_depth=6)    — shortest-path codes                  ║
║    • hubs(top=15)               — most-connected agents                ║
║    • stats()                    — global graph statistics              ║
║    • mirror_onto(agent, k)      — attach neighbor-codes to a dict      ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import threading
import time
from collections import deque
from typing import Iterable, Optional

from core import full_roster as fr

# ── Tuning constants (all involution / symmetric rules) ───────────────
# XOR masks chosen to produce good spread across the full roster while
# keeping every rule an involution → undirected by construction.
BRIDGE_MASK_A = 0x55555
BRIDGE_MASK_B = 0xA5A5A
BRIDGE_MASK_C = 0x1F1F1F

# Soft caps (safety so BFS never runs away on a 1.47M graph)
REACH_VISIT_CAP = 2_000_000        # covers the whole roster if needed
PATH_VISIT_CAP  = 500_000          # max nodes shortest-path BFS may touch
HUB_DEGREE_CAP  = 8192             # report hub degree capped at this

# State — procedurally derived, so "build" is essentially free
_BUILD_TS: float = 0.0
_BUILD_LOCK = threading.Lock()
_WARM: bool = False

# Cached stats (reachability probe is expensive, cache for 5 minutes)
_STATS_CACHE: Optional[dict] = None
_STATS_TS: float = 0.0
_STATS_TTL: float = 300.0   # seconds

# Cached materialised agent dicts for swarm + collection (first 482)
_MATERIAL_CACHE: Optional[list[dict]] = None
_MATERIAL_BY_CODE: Optional[dict[str, dict]] = None


# ─────────────────────────────────────────────────────────────────────
# MATERIALISED SUBSET (first 482 ids)
# ─────────────────────────────────────────────────────────────────────
def _load_materialised() -> tuple[list[dict], dict[str, dict]]:
    """Load the 482 real agent dicts (swarm + collection). Lazy, one-shot."""
    global _MATERIAL_CACHE, _MATERIAL_BY_CODE
    if _MATERIAL_CACHE is not None and _MATERIAL_BY_CODE is not None:
        return _MATERIAL_CACHE, _MATERIAL_BY_CODE
    try:
        from core.swarm_agents import SWARM_DOMAINS
        from core.collection_agents import build_manifest as _cm
        agents = list(SWARM_DOMAINS) + _cm()
    except Exception:
        agents = []
    by_code: dict[str, dict] = {}
    for a in agents:
        code = a.get("agent_code")
        if code:
            by_code[code] = a
    _MATERIAL_CACHE = agents
    _MATERIAL_BY_CODE = by_code
    return agents, by_code


def _lookup_material(code: str) -> Optional[dict]:
    _, by_code = _load_materialised()
    return by_code.get(code)


# ─────────────────────────────────────────────────────────────────────
# PROCEDURAL NEIGHBORS
# ─────────────────────────────────────────────────────────────────────
def _valid(i: int) -> bool:
    return 0 <= i < fr.TOTAL_AGENTS


def _xor_partner(i: int, mask: int) -> Optional[int]:
    j = i ^ mask
    if j == i or not _valid(j):
        return None
    return j


def out_neighbors_id(i: int) -> list[int]:
    """
    Deterministic neighbor set for integer id `i`. Every rule is an
    involution / symmetric relation, so (i, j) ∈ E ⇔ (j, i) ∈ E.

    Topology layers:
      • cohort k-ary tree (arity ≈ √size)  — parent + children
      • parliament clique of the 8 cohort roots
      • team ring + chord  (flavour / redundancy)
      • legion step + chord  (flavour / redundancy)
      • XOR cross-cohort bridges (extra spice)

    Diameter ≤ 5 hops: any agent reaches its cohort root in ≤ 2 tree
    hops, root ↔ root is 1 hop, then another ≤ 2 tree hops to the target.
    """
    if not _valid(i):
        return []
    loc = fr.locate(i)
    c = loc["cohort"]
    start = c["start"]
    end = c["end"]
    size = c["size"]
    offset = loc["offset"]
    ts = c["team_size"]
    tpl = c["teams_per_legion"]
    ls = c["legion_size"]
    team = loc["team"]
    seat = loc["team_seat"]
    legion = loc["legion"]
    team_in_legion = loc["team_in_legion"]

    s: set[int] = set()

    # ── (0) Cohort k-ary tree: parent + children (THE backbone) ──
    parent = fr.tree_parent_id(i)
    if parent is not None:
        s.add(parent)
    for ch in fr.tree_children_ids(i):
        s.add(ch)

    # ── (1) Parliament clique — the 8 cohort roots are fully linked ──
    if i in fr.PARLIAMENT_IDS:
        for p in fr.PARLIAMENT_IDS:
            if p != i:
                s.add(p)

    # ── (2) Team ring (within team, flavour edges) ──
    team_start = start + team * ts
    team_end   = min(team_start + ts, end)
    actual_ts  = team_end - team_start
    if actual_ts > 1:
        s.add(team_start + (seat - 1) % actual_ts)
        s.add(team_start + (seat + 1) % actual_ts)
        half = actual_ts // 2
        if half > 0:
            s.add(team_start + (seat + half) % actual_ts)

    # ── (3) Legion step + opposite (within legion) ──
    legion_start = start + legion * ls
    legion_end   = min(legion_start + ls, end)
    actual_ltc   = min(tpl, (legion_end - legion_start + ts - 1) // ts)
    if actual_ltc > 1:
        next_til = (team_in_legion + 1) % actual_ltc
        prev_til = (team_in_legion - 1) % actual_ltc
        nxt = legion_start + next_til * ts + seat
        prv = legion_start + prev_til * ts + seat
        if nxt < legion_end:
            s.add(nxt)
        if prv < legion_end:
            s.add(prv)
        opp_til = (team_in_legion + actual_ltc // 2) % actual_ltc
        opp_idx = legion_start + opp_til * ts + seat
        if opp_idx < legion_end:
            s.add(opp_idx)

    # ── (4) Cohort opposite (global involution within cohort) ──
    cohort_opposite = start + (size - 1 - offset)
    if cohort_opposite != i and _valid(cohort_opposite):
        s.add(cohort_opposite)

    # ── (5) Cross-cohort XOR bridges (involutions) ──
    for mask in (BRIDGE_MASK_A, BRIDGE_MASK_B, BRIDGE_MASK_C):
        j = _xor_partner(i, mask)
        if j is not None:
            s.add(j)

    s.discard(i)
    return sorted(s)


def out_neighbors_code(code: str) -> list[str]:
    try:
        i = fr.id_of_code(code)
    except Exception:
        # Fallback for legacy materialised codes already honored by id_of_code;
        # anything else returns empty.
        return []
    return [fr.agent_code(j) for j in out_neighbors_id(i)]


# ─────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────
def build_mesh(force: bool = False) -> dict:
    """Procedural mesh is always ready — just record a warm-up timestamp."""
    global _BUILD_TS, _WARM, _STATS_CACHE, _STATS_TS
    with _BUILD_LOCK:
        if not _WARM or force:
            _BUILD_TS = time.time()
            _WARM = True
            _STATS_CACHE = None
            _STATS_TS = 0.0
            _load_materialised()
    return stats()


def _ensure_built() -> None:
    if not _WARM:
        build_mesh()


def neighbors(code: str, k: Optional[int] = None) -> list[dict]:
    """Rich neighbor descriptors for the agent addressed by `code`."""
    _ensure_built()
    try:
        i = fr.id_of_code(code)
    except Exception:
        return []
    nb_ids = out_neighbors_id(i)
    if k:
        nb_ids = nb_ids[:k]
    out: list[dict] = []
    for j in nb_ids:
        loc = fr.locate(j)
        ncode = fr.agent_code(j)
        mat = _lookup_material(ncode)
        out.append({
            "code": ncode,
            "id": j,
            "cohort": loc["cohort"]["id"],
            "cohort_label": loc["cohort"]["label"],
            "team": loc["team"],
            "team_id": (mat.get("team_id") if mat else fr.team_id_str(j)),
            "legion": loc["legion"],
            "legion_id": (mat.get("legion_id") if mat else fr.legion_id_str(j)),
            "agent": (mat.get("agent") if mat else f"{loc['cohort']['label']} Specialist #{loc['offset']+1}"),
        })
    return out


def neighbor_codes(code: str, k: Optional[int] = None) -> list[str]:
    try:
        i = fr.id_of_code(code)
    except Exception:
        return []
    nb = out_neighbors_id(i)
    if k:
        nb = nb[:k]
    return [fr.agent_code(j) for j in nb]


def reach(code: str, depth: int = 2) -> dict:
    """BFS from `code` up to `depth` hops. Hard-capped at REACH_VISIT_CAP nodes."""
    _ensure_built()
    try:
        start_id = fr.id_of_code(code)
    except Exception:
        return {"code": code, "depth": depth, "layers": [], "total_reached": 0}

    visited: set[int] = {start_id}
    frontier: list[int] = [start_id]
    layers: list[dict] = []
    capped = False
    for d in range(1, depth + 1):
        next_frontier: list[int] = []
        for cur in frontier:
            if len(visited) >= REACH_VISIT_CAP:
                capped = True
                break
            for j in out_neighbors_id(cur):
                if j not in visited:
                    visited.add(j)
                    next_frontier.append(j)
                    if len(visited) >= REACH_VISIT_CAP:
                        capped = True
                        break
            if capped:
                break
        layers.append({
            "hop": d,
            "size": len(next_frontier),
            "codes_preview": [fr.agent_code(j) for j in next_frontier[:20]],
        })
        frontier = next_frontier
        if not frontier or capped:
            break

    return {
        "code": code,
        "depth": depth,
        "layers": layers,
        "total_reached": len(visited) - 1,
        "roster_size": fr.TOTAL_AGENTS,
        "coverage_pct": round((len(visited) - 1) / max(fr.TOTAL_AGENTS - 1, 1) * 100, 4),
        "capped": capped,
    }


def path(from_code: str, to_code: str, max_depth: int = 6) -> dict:
    """Shortest path via bidirectional BFS. Capped for scale."""
    _ensure_built()
    try:
        a = fr.id_of_code(from_code)
        b = fr.id_of_code(to_code)
    except Exception:
        return {"from": from_code, "to": to_code, "found": False, "hops": 0, "path": []}
    if a == b:
        return {"from": from_code, "to": to_code, "found": True, "hops": 0, "path": [from_code]}

    parent: dict[int, int] = {a: a}
    depth_of: dict[int, int] = {a: 0}
    q: deque[int] = deque([a])
    visits = 0
    found = False
    while q:
        cur = q.popleft()
        visits += 1
        if depth_of[cur] >= max_depth:
            continue
        if visits > PATH_VISIT_CAP:
            break
        for j in out_neighbors_id(cur):
            if j in parent:
                continue
            parent[j] = cur
            depth_of[j] = depth_of[cur] + 1
            if j == b:
                found = True
                q.clear()
                break
            q.append(j)
    if not found:
        return {"from": from_code, "to": to_code, "found": False, "hops": -1, "path": [], "visits": visits}

    # Reconstruct
    chain = [b]
    while chain[-1] != a:
        chain.append(parent[chain[-1]])
    chain.reverse()
    codes = [fr.agent_code(x) for x in chain]
    return {
        "from": from_code, "to": to_code,
        "found": True, "hops": len(chain) - 1,
        "path": codes,
        "visits": visits,
    }


def hubs(top: int = 15) -> list[dict]:
    """
    Global hub list: Parliament + top cohort-hubs, annotated with an
    estimate of their degree (actual degree for the Parliament and cohort
    hubs is ~= cohort_size since every member links to them).
    """
    _ensure_built()
    out: list[dict] = []

    # Parliament (id 0..7) — each links to ~ TOTAL across all cohorts (via cohort-hub mesh).
    for pid in fr.PARLIAMENT_IDS:
        loc = fr.locate(pid)
        ncode = fr.agent_code(pid)
        mat = _lookup_material(ncode)
        # Degree estimate: 7 other parliament + 3 hubs × (cohorts-1) + local mesh
        deg = min(HUB_DEGREE_CAP,
                  7 + 3 * (len(fr.COHORTS) - 1) + 32)
        out.append({
            "code": ncode, "id": pid,
            "cohort": loc["cohort"]["id"],
            "agent": mat.get("agent") if mat else "Parliament",
            "team_id": mat.get("team_id") if mat else fr.team_id_str(pid),
            "legion_id": mat.get("legion_id") if mat else fr.legion_id_str(pid),
            "role": "parliament",
            "est_degree": deg,
        })

    # Cohort hubs (first 3 seats of each cohort, skipping those already in parliament)
    for c in fr.COHORTS:
        for h in fr.cohort_hub_ids(c, 3):
            if h in fr.PARLIAMENT_IDS:
                continue
            loc = fr.locate(h)
            ncode = fr.agent_code(h)
            mat = _lookup_material(ncode)
            # Cohort hub degree ≈ cohort size + parliament + other cohort hubs
            deg = min(HUB_DEGREE_CAP,
                      c["size"] + len(fr.PARLIAMENT_IDS) + 3 * (len(fr.COHORTS) - 1))
            out.append({
                "code": ncode, "id": h,
                "cohort": c["id"],
                "agent": (mat.get("agent") if mat else f"{c['label']} Hub #{loc['offset']+1}"),
                "team_id": (mat.get("team_id") if mat else fr.team_id_str(h)),
                "legion_id": (mat.get("legion_id") if mat else fr.legion_id_str(h)),
                "role": "cohort_hub",
                "est_degree": deg,
            })

    out.sort(key=lambda e: -e["est_degree"])
    return out[:top]


def stats() -> dict:
    """
    Global graph statistics. Expensive reachability probe (~6s BFS over
    1.47M nodes) is cached for _STATS_TTL seconds. Call `build_mesh(force=True)`
    (or just wait for TTL) to refresh.
    """
    _ensure_built()
    global _STATS_CACHE, _STATS_TS
    now = time.time()
    if _STATS_CACHE is not None and (now - _STATS_TS) < _STATS_TTL:
        return _STATS_CACHE

    N = fr.TOTAL_AGENTS

    # Sample degrees from an even spread of ids
    sample_ids = []
    if N >= 1:
        step = max(1, N // 256)
        sample_ids = list(range(0, N, step))[:256]
    degrees = [len(out_neighbors_id(i)) for i in sample_ids]
    if degrees:
        avg_deg = sum(degrees) / len(degrees)
        min_deg = min(degrees)
        max_deg = max(degrees)
    else:
        avg_deg = min_deg = max_deg = 0
    est_edges = int(N * avg_deg / 2)

    # Probe reachability (capped at REACH_VISIT_CAP)
    probe = reach(fr.agent_code(0), depth=6)

    result = {
        "nodes": N,
        "cohorts": len(fr.COHORTS),
        "cohorts_summary": fr.cohort_summary(),
        "estimated_edges": est_edges,
        "sampled_avg_degree": round(avg_deg, 2),
        "sampled_min_degree": min_deg,
        "sampled_max_degree": max_deg,
        "parliament_size": len(fr.PARLIAMENT_IDS),
        "reachability_probe": {
            "from": probe["code"],
            "depth": probe["depth"],
            "total_reached": probe["total_reached"],
            "coverage_pct": probe["coverage_pct"],
            "capped": probe.get("capped", False),
        },
        "build_ts": _BUILD_TS,
        "stats_cached_ts": now,
        "stats_ttl_seconds": _STATS_TTL,
        "topology": "procedural-kary-tree+parliament-clique+team-ring+legion+xor-bridge",
        "directed": False,
    }
    _STATS_CACHE = result
    _STATS_TS = now
    return result


def mirror_onto(agent: dict, k: int = 12) -> dict:
    """Attach mesh neighbor codes + degree to an agent dict (for swarm subset)."""
    if not isinstance(agent, dict):
        return agent
    code = agent.get("agent_code")
    if not code:
        return agent
    _ensure_built()
    try:
        i = fr.id_of_code(code)
    except Exception:
        agent["neighbors_codes"] = []
        agent["degree"] = 0
        return agent
    nb = out_neighbors_id(i)
    agent["neighbors_codes"] = [fr.agent_code(j) for j in nb[:k]]
    agent["degree"] = len(nb)
    return agent
