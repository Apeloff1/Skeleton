"""
Cold-storage API & Legion discourse endpoints.

All prefixed /api/galaxy-studio/swarm/*  to stay under the existing hub.
"""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import cold_storage as cs
from core import collection_agents as ca
from core import legion_discourse as legion
from core import agent_ledger as ledger
from core import whisper_network as whispers
from core import platoons as platoons_mod
from core import jeeves_capabilities as jcap
from core import agent_mesh as mesh
from core.swarm_agents import (
    SWARM_DOMAINS, BY_ID, BY_NUMBER, BY_CATEGORY, BY_TEAM, BY_LEGION,
)

router = APIRouter(prefix="/api/galaxy-studio/swarm", tags=["swarm-cold-legion"])


# ── Cold Storage ────────────────────────────────────────────────────────
@router.get("/cold/stats")
def cold_stats() -> dict:
    return cs.stats()


@router.get("/cold/registry")
def cold_registry(status: str | None = None, limit: int = 400) -> dict:
    return {"rows": cs.registry_list(status=status, limit=limit)}


class FreezeReq(BaseModel):
    name: str
    drop_after: bool = True
    compact: bool = True
    force: bool = False


@router.post("/cold/freeze")
def cold_freeze(req: FreezeReq) -> dict:
    try:
        return cs.freeze(req.name, drop_after=req.drop_after, compact=req.compact, force=req.force)
    except Exception as ex:
        raise HTTPException(400, str(ex))


class ThawReq(BaseModel):
    name: str
    mark_hot: bool = True


@router.post("/cold/thaw")
def cold_thaw(req: ThawReq) -> dict:
    return cs.thaw(req.name, mark_hot=req.mark_hot)


@router.get("/cold/query/{name}")
def cold_query(name: str, limit: int = 50, offset: int = 0, key: str | None = None, value: str | None = None) -> dict:
    filt = {key: value} if key and value is not None else None
    rows = cs.cold_query(name, filter=filt, limit=min(max(limit, 1), 500), offset=max(offset, 0))
    return {"name": name, "count": len(rows), "rows": rows}


class FreezeAllReq(BaseModel):
    min_storage_kb: int = 500
    skip_protected: bool = True
    dry_run: bool = False
    limit: int | None = None


@router.post("/cold/freeze-all")
def cold_freeze_all(req: FreezeAllReq) -> dict:
    return cs.freeze_all(
        min_storage_bytes=req.min_storage_kb * 1024,
        skip_protected=req.skip_protected,
        dry_run=req.dry_run,
        limit=req.limit,
    )


@router.post("/cold/evictor/start")
def cold_evictor_start() -> dict:
    return {"started": cs.start_evictor()}


@router.post("/cold/evictor/stop")
def cold_evictor_stop() -> dict:
    cs.stop_evictor()
    return {"stopped": True}


@router.post("/cold/evictor/tick")
def cold_evictor_tick(ttl: int | None = None, max_freeze: int = 10) -> dict:
    return cs.evictor_tick(ttl=ttl or cs.COLD_TTL_SEC, max_freeze=max_freeze)


# ── Collection Agents ───────────────────────────────────────────────────
@router.get("/collection-agents")
def coll_agents(category: str | None = None, q: str | None = None, limit: int = 500) -> dict:
    rows = ca.build_manifest()
    if category:
        rows = [r for r in rows if r["category"] == category]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["id"] or ql in r["domain"].lower() or ql in r["agent"].lower()]
    return {"total": len(rows), "agents": rows[:limit]}


@router.get("/collection-agents/categories")
def coll_agent_categories() -> dict:
    hist = ca.category_histogram()
    return {"total_agents": ca.total_agents(), "categories": hist}


# ── Legion Discourse ────────────────────────────────────────────────────
class LegionReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    phase: str = Field(..., min_length=1)
    game_ctx: dict[str, Any] = Field(default_factory=dict)
    team_categories: list[str] | None = None
    seat_limit: int = 999               # uncapped — entire team participates
    max_full_swarm_voices: int = 1000   # accommodate entire 482-agent roster
    persist: bool = True


@router.post("/discourse/legion/simulate")
def legion_simulate(req: LegionReq) -> dict:
    return legion.simulate_network(
        build_id=req.build_id,
        phase=req.phase,
        game_ctx=req.game_ctx,
        team_categories=req.team_categories,
        seat_limit=req.seat_limit,
        max_full_swarm_voices=req.max_full_swarm_voices,
        persist=req.persist,
    )


@router.get("/discourse/legion/build/{build_id}")
def legion_for_build(build_id: str, limit: int = 20) -> dict:
    return {"build_id": build_id, "logs": legion.get_for_build(build_id, limit)}


@router.get("/discourse/legion/stats")
def legion_stats() -> dict:
    return legion.network_stats()


# ── Jeeves Capabilities (mirrored across every agent) ─────────────────
@router.get("/capabilities")
def capabilities_catalog() -> dict:
    """Full canonical Jeeves capability catalog — personas, conversation
    skills, tutor knowledge, production powers, and the quality bar."""
    return jcap.get_catalog()


# ── Agent Mesh (the spider-web across all 1.47M agents) ────────────────
@router.get("/mesh/stats")
def mesh_stats() -> dict:
    return mesh.stats()


@router.post("/mesh/rebuild")
def mesh_rebuild() -> dict:
    s = mesh.build_mesh(force=True)
    # Stamp swarm-agent dicts with neighbors_codes now that mesh is rebuilt
    try:
        from core.swarm_agents import _stamp_mesh_neighbors as _stamp
        _stamp()
    except Exception:
        pass
    return s


@router.get("/mesh/neighbors/{code}")
def mesh_neighbors(code: str, k: int = 12) -> dict:
    nb = mesh.neighbors(code, k=k)
    return {"code": code, "count": len(nb), "neighbors": nb}


@router.get("/mesh/reach/{code}")
def mesh_reach(code: str, depth: int = 2) -> dict:
    if depth < 1 or depth > 6:
        raise HTTPException(400, "depth must be 1..6")
    return mesh.reach(code, depth=depth)


@router.get("/mesh/path/{from_code}/{to_code}")
def mesh_path(from_code: str, to_code: str, max_depth: int = 6) -> dict:
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(400, "max_depth must be 1..10")
    return mesh.path(from_code, to_code, max_depth=max_depth)


@router.get("/mesh/hubs")
def mesh_hubs(top: int = 15) -> dict:
    return {"top": top, "hubs": mesh.hubs(top=min(max(top, 1), 100))}


# ── Full Roster (every single agent in the constellation) ──────────────
@router.get("/roster/manifest")
def roster_manifest() -> dict:
    from core import full_roster as fr
    return fr.manifest()


@router.get("/roster/cohort/{cohort_id}")
def roster_cohort(cohort_id: str, limit: int = 50, offset: int = 0) -> dict:
    from core import full_roster as fr
    c = fr.cohort_by_id(cohort_id)
    if not c:
        raise HTTPException(404, f"unknown cohort '{cohort_id}'")
    limit = max(1, min(limit, 500))
    offset = max(0, min(offset, c["size"]))
    end = min(offset + limit, c["size"])
    rows = []
    for off in range(offset, end):
        aid = c["start"] + off
        rows.append({
            "id": aid,
            "code": fr.agent_code(aid),
            "team_id": fr.team_id_str(aid),
            "legion_id": fr.legion_id_str(aid),
        })
    return {
        "cohort": c["id"],
        "label": c["label"],
        "size": c["size"],
        "offset": offset,
        "returned": len(rows),
        "rows": rows,
    }


@router.get("/roster/resolve/{code}")
def roster_resolve(code: str) -> dict:
    from core import full_roster as fr
    try:
        aid = fr.id_of_code(code)
    except Exception as ex:
        raise HTTPException(404, f"cannot resolve code '{code}': {ex}")
    loc = fr.locate(aid)
    c = loc["cohort"]
    return {
        "code": code,
        "id": aid,
        "cohort": c["id"],
        "cohort_label": c["label"],
        "team": loc["team"],
        "team_seat": loc["team_seat"],
        "team_id": fr.team_id_str(aid),
        "legion": loc["legion"],
        "legion_id": fr.legion_id_str(aid),
        "is_parliament": aid in fr.PARLIAMENT_IDS,
        "is_cohort_hub": aid in fr.cohort_hub_ids(c, 4),
    }


@router.get("/census")
def census() -> dict:
    from core.swarm_agents import SWARM_DOMAINS, BY_CATEGORY, BY_TEAM, BY_LEGION
    from core import full_roster as fr
    return {
        "swarm_agents": len(SWARM_DOMAINS),
        "collection_agents": ca.total_agents(),
        "materialised_agents": len(SWARM_DOMAINS) + ca.total_agents(),
        "full_roster_agents": fr.TOTAL_AGENTS,
        "roster_cohorts": fr.cohort_summary(),
        "total_agents": fr.TOTAL_AGENTS,   # headline figure (1,473,844)
        "swarm_categories": {c: len(v) for c, v in BY_CATEGORY.items()},
        "swarm_teams": {t: len(v) for t, v in BY_TEAM.items()},
        "swarm_legions": {l: len(v) for l, v in BY_LEGION.items()},
        "collection_categories": ca.category_histogram(),
        "cold_storage": cs.stats(),
        "legion_logs": legion.network_stats()["legion_logs"],
        "whispers": whispers.stats(),
        "ledger_total_entries": ledger._ledger.estimated_document_count(),
        "capabilities": jcap.capability_summary(),
    }


@router.get("/capabilities/summary")
def capabilities_summary_endpoint() -> dict:
    return jcap.capability_summary()


@router.get("/capabilities/personas/{name}")
def capabilities_persona(name: str) -> dict:
    p = jcap.get_persona(name)
    if not p:
        raise HTTPException(404, f"Unknown persona '{name}'")
    return p


@router.get("/capabilities/agent/{agent_code}")
def capabilities_for_agent(agent_code: str) -> dict:
    """Return the capability block attached to a specific agent."""
    # swarm?
    for d in SWARM_DOMAINS:
        if d.get("agent_code") == agent_code:
            return {"source": "swarm", "agent_code": agent_code,
                    "agent": d.get("agent"), "capabilities": d.get("capabilities")}
    # collection?
    for c in ca.build_manifest():
        if c.get("agent_code") == agent_code:
            return {"source": "collection", "agent_code": agent_code,
                    "agent": c.get("agent"), "capabilities": c.get("capabilities")}
    raise HTTPException(404, f"Unknown agent_code '{agent_code}'")


@router.get("/capabilities/roster/coverage")
def capabilities_coverage() -> dict:
    """Verify every agent has capabilities mirrored."""
    total = 0
    with_caps = 0
    for d in SWARM_DOMAINS:
        total += 1
        if "capabilities" in d:
            with_caps += 1
    for c in ca.build_manifest():
        total += 1
        if "capabilities" in c:
            with_caps += 1
    return {
        "total_agents": total,
        "agents_with_capabilities": with_caps,
        "coverage_pct": round(with_caps / max(total, 1) * 100, 2),
        "summary": jcap.capability_summary(),
    }
@router.get("/census")
def census() -> dict:
    from core.swarm_agents import SWARM_DOMAINS, BY_CATEGORY, BY_TEAM, BY_LEGION
    return {
        "swarm_agents": len(SWARM_DOMAINS),
        "collection_agents": ca.total_agents(),
        "total_agents": len(SWARM_DOMAINS) + ca.total_agents(),
        "swarm_categories": {c: len(v) for c, v in BY_CATEGORY.items()},
        "swarm_teams": {t: len(v) for t, v in BY_TEAM.items()},
        "swarm_legions": {l: len(v) for l, v in BY_LEGION.items()},
        "collection_categories": ca.category_histogram(),
        "cold_storage": cs.stats(),
        "legion_logs": legion.network_stats()["legion_logs"],
        "whispers": whispers.stats(),
        "ledger_total_entries": ledger._ledger.estimated_document_count(),
    }


# ── Teams / Legions / Agent Numbering ──────────────────────────────────
@router.get("/teams")
def teams_list() -> dict:
    out = []
    for tid, members in BY_TEAM.items():
        leader = members[0] if members else None
        out.append({
            "team_id": tid,
            "team_name": leader.get("team_name") if leader else tid,
            "category": leader.get("category") if leader else None,
            "legion_id": leader.get("legion_id") if leader else None,
            "leader_code": leader.get("agent_code") if leader else None,
            "seats": len(members),
            "members": [{"code": m["agent_code"], "agent": m["agent"], "seat": m.get("team_seat")} for m in members],
        })
    return {"total_teams": len(out), "teams": sorted(out, key=lambda t: t["team_id"])}


@router.get("/teams/{team_id}")
def team_detail(team_id: str) -> dict:
    members = BY_TEAM.get(team_id, [])
    if not members:
        raise HTTPException(404, f"Team '{team_id}' not found")
    return {"team_id": team_id, "seats": len(members), "members": members}


@router.get("/legions")
def legions_list() -> dict:
    out = []
    for lid, members in BY_LEGION.items():
        # teams in this legion
        team_ids = sorted({m["team_id"] for m in members})
        out.append({
            "legion_id": lid,
            "legion_name": members[0].get("legion_name") if members else lid,
            "team_ids": team_ids,
            "seats": len(members),
            "agent_code_range": f"{min(m['agent_code'] for m in members)} – {max(m['agent_code'] for m in members)}" if members else None,
        })
    return {"total_legions": len(out), "legions": sorted(out, key=lambda l: l["legion_id"])}


@router.get("/legions/{legion_id}")
def legion_detail(legion_id: str) -> dict:
    members = BY_LEGION.get(legion_id, [])
    if not members:
        raise HTTPException(404, f"Legion '{legion_id}' not found")
    team_ids = sorted({m["team_id"] for m in members})
    return {
        "legion_id": legion_id,
        "legion_name": members[0].get("legion_name"),
        "team_ids": team_ids,
        "seats": len(members),
        "members": members,
    }


@router.get("/agents/by-number/{number}")
def agent_by_number(number: int) -> dict:
    agent = BY_NUMBER.get(number)
    if agent:
        return {"source": "swarm", "agent": agent}
    # Check collection-agents
    for c in ca.build_manifest():
        if c.get("agent_number") == number:
            return {"source": "collection", "agent": c}
    raise HTTPException(404, f"Agent #{number} not found")


# ── Agent Ledger (per-agent notebook) ──────────────────────────────────
@router.get("/ledger/notebook/{agent_code}")
def ledger_notebook(agent_code: str, limit: int = 30) -> dict:
    return {"agent_code": agent_code, "entries": ledger.notebook(agent_code, min(max(limit, 1), 500))}


@router.get("/ledger/stats")
def ledger_stats_endpoint(top: int = 15) -> dict:
    return ledger.stats(top=top)


@router.get("/ledger/build/{build_id}")
def ledger_for_build(build_id: str, limit: int = 200) -> dict:
    return {"build_id": build_id, "entries": ledger.contributions_for_build(build_id, min(max(limit, 1), 1000))}


# ── Whisper Network ────────────────────────────────────────────────────
@router.get("/whispers/recent/{recipient_code}")
def whispers_recent(recipient_code: str, limit: int = 20) -> dict:
    return {"recipient_code": recipient_code, "whispers": whispers.recent(recipient_code, min(max(limit, 1), 200))}


@router.get("/whispers/build/{build_id}")
def whispers_for_build(build_id: str, limit: int = 200) -> dict:
    return {"build_id": build_id, "whispers": whispers.for_build(build_id, min(max(limit, 1), 500))}


@router.get("/whispers/stats")
def whispers_stats_endpoint() -> dict:
    return whispers.stats()


# ── Platoons (per-build-phase microteams) ──────────────────────────────
@router.get("/platoons/roster/stats")
def platoon_roster_stats() -> dict:
    return {
        "total_agents_in_roster": platoons_mod.total_agent_count(),
        "swarm_agents": len(SWARM_DOMAINS),
        "collection_agents": ca.total_agents(),
    }


class PlatoonReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    phase_id: str = Field(..., min_length=1)
    game_ctx: dict[str, Any] = Field(default_factory=dict)
    rotation_idx: int = 0
    prev_handoff: str | None = None
    rounds: int = 2
    size: int = 5
    persist: bool = True


@router.post("/platoons/run")
def platoon_run(req: PlatoonReq) -> dict:
    return platoons_mod.run_platoon(
        build_id=req.build_id, phase_id=req.phase_id, game_ctx=req.game_ctx,
        rotation_idx=req.rotation_idx, prev_handoff=req.prev_handoff,
        rounds=req.rounds, size=req.size, persist=req.persist,
    )


class ChainReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    batch_num: int = 1
    game_ctx: dict[str, Any] = Field(default_factory=dict)
    phase_ids: list[str] = Field(default_factory=lambda: [f"p{i:02d}" for i in range(1, 11)])
    rounds: int = 2
    size: int = 5


@router.post("/platoons/chain")
def platoon_chain(req: ChainReq) -> dict:
    return platoons_mod.chain_for_batch(
        build_id=req.build_id, batch_num=req.batch_num, game_ctx=req.game_ctx,
        phase_ids=req.phase_ids, rounds=req.rounds, size=req.size,
    )


@router.get("/platoons/build/{build_id}")
def platoons_for_build(build_id: str, limit: int = 200) -> dict:
    return {"build_id": build_id, "platoons": platoons_mod.platoons_for_build(build_id, limit)}


@router.get("/platoons/coverage/{build_id}")
def platoons_coverage(build_id: str) -> dict:
    return platoons_mod.coverage_stats(build_id)


@router.get("/platoons/participation/{build_id}")
def platoons_participation(build_id: str, limit: int = 500) -> dict:
    return {"build_id": build_id, "rows": platoons_mod.participation_rows(build_id, limit)}


class SweepReq(BaseModel):
    build_id: str
    game_ctx: dict[str, Any] = Field(default_factory=dict)


@router.post("/platoons/sweep")
def platoons_sweep(req: SweepReq) -> dict:
    return platoons_mod.force_participation_sweep(req.build_id, req.game_ctx)
