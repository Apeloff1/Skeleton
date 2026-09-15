"""Cold-storage, swarm roster, discourse, mesh, ledger and platoon API.

All endpoints are rooted at ``/api/galaxy-studio/swarm``. This module is the
canonical swarm operations surface; endpoint registration is intentionally
unique so FastAPI routing never depends on declaration order.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import agent_ledger as ledger
from core import agent_mesh as mesh
from core import cold_storage as cs
from core import collection_agents as ca
from core import jeeves_capabilities as jcap
from core import legion_discourse as legion
from core import platoons as platoons_mod
from core import whisper_network as whispers
from core.swarm_agents import BY_LEGION, BY_NUMBER, BY_TEAM, SWARM_DOMAINS

router = APIRouter(prefix="/api/galaxy-studio/swarm", tags=["swarm-cold-legion"])


def _bounded(value: int, *, low: int, high: int) -> int:
    return min(max(value, low), high)


# ── Cold storage ─────────────────────────────────────────────────────────────


@router.get("/cold/stats")
def cold_stats() -> dict:
    return cs.stats()


@router.get("/cold/registry")
def cold_registry(status: str | None = None, limit: int = 400) -> dict:
    return {"rows": cs.registry_list(status=status, limit=_bounded(limit, low=1, high=1000))}


class FreezeReq(BaseModel):
    name: str
    drop_after: bool = True
    compact: bool = True
    force: bool = False


@router.post("/cold/freeze")
def cold_freeze(req: FreezeReq) -> dict:
    try:
        return cs.freeze(
            req.name,
            drop_after=req.drop_after,
            compact=req.compact,
            force=req.force,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


class ThawReq(BaseModel):
    name: str
    mark_hot: bool = True


@router.post("/cold/thaw")
def cold_thaw(req: ThawReq) -> dict:
    return cs.thaw(req.name, mark_hot=req.mark_hot)


@router.get("/cold/query/{name}")
def cold_query(
    name: str,
    limit: int = 50,
    offset: int = 0,
    key: str | None = None,
    value: str | None = None,
) -> dict:
    filt = {key: value} if key and value is not None else None
    rows = cs.cold_query(
        name,
        filter=filt,
        limit=_bounded(limit, low=1, high=500),
        offset=max(offset, 0),
    )
    return {"name": name, "count": len(rows), "rows": rows}


class FreezeAllReq(BaseModel):
    min_storage_kb: int = 500
    skip_protected: bool = True
    dry_run: bool = False
    limit: int | None = None


@router.post("/cold/freeze-all")
def cold_freeze_all(req: FreezeAllReq) -> dict:
    return cs.freeze_all(
        min_storage_bytes=max(req.min_storage_kb, 0) * 1024,
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
    return cs.evictor_tick(
        ttl=ttl or cs.COLD_TTL_SEC,
        max_freeze=_bounded(max_freeze, low=1, high=500),
    )


# ── Collection agents ────────────────────────────────────────────────────────


@router.get("/collection-agents")
def collection_agents(category: str | None = None, q: str | None = None, limit: int = 500) -> dict:
    rows = ca.build_manifest()
    if category:
        rows = [row for row in rows if row["category"] == category]
    if q:
        query = q.casefold()
        rows = [
            row
            for row in rows
            if query in row["id"].casefold()
            or query in row["domain"].casefold()
            or query in row["agent"].casefold()
        ]
    bounded_limit = _bounded(limit, low=1, high=2000)
    return {"total": len(rows), "agents": rows[:bounded_limit]}


@router.get("/collection-agents/categories")
def collection_agent_categories() -> dict:
    return {"total_agents": ca.total_agents(), "categories": ca.category_histogram()}


# ── Legion discourse ─────────────────────────────────────────────────────────


class LegionReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    phase: str = Field(..., min_length=1)
    game_ctx: dict[str, Any] = Field(default_factory=dict)
    team_categories: list[str] | None = None
    seat_limit: int = 999
    max_full_swarm_voices: int = 1000
    persist: bool = True


@router.post("/discourse/legion/simulate")
def legion_simulate(req: LegionReq) -> dict:
    return legion.simulate_network(
        build_id=req.build_id,
        phase=req.phase,
        game_ctx=req.game_ctx,
        team_categories=req.team_categories,
        seat_limit=_bounded(req.seat_limit, low=1, high=5000),
        max_full_swarm_voices=_bounded(req.max_full_swarm_voices, low=1, high=5000),
        persist=req.persist,
    )


@router.get("/discourse/legion/build/{build_id}")
def legion_for_build(build_id: str, limit: int = 20) -> dict:
    return {
        "build_id": build_id,
        "logs": legion.get_for_build(build_id, _bounded(limit, low=1, high=500)),
    }


@router.get("/discourse/legion/stats")
def legion_stats() -> dict:
    return legion.network_stats()


# ── Jeeves capabilities ──────────────────────────────────────────────────────


@router.get("/capabilities")
def capabilities_catalog() -> dict:
    return jcap.get_catalog()


@router.get("/capabilities/summary")
def capabilities_summary() -> dict:
    return jcap.capability_summary()


@router.get("/capabilities/personas/{name}")
def capabilities_persona(name: str) -> dict:
    persona = jcap.get_persona(name)
    if not persona:
        raise HTTPException(404, f"Unknown persona '{name}'")
    return persona


@router.get("/capabilities/agent/{agent_code}")
def capabilities_for_agent(agent_code: str) -> dict:
    for domain in SWARM_DOMAINS:
        if domain.get("agent_code") == agent_code:
            return {
                "source": "swarm",
                "agent_code": agent_code,
                "agent": domain.get("agent"),
                "capabilities": domain.get("capabilities"),
            }
    for row in ca.build_manifest():
        if row.get("agent_code") == agent_code:
            return {
                "source": "collection",
                "agent_code": agent_code,
                "agent": row.get("agent"),
                "capabilities": row.get("capabilities"),
            }
    raise HTTPException(404, f"Unknown agent_code '{agent_code}'")


@router.get("/capabilities/roster/coverage")
def capabilities_coverage() -> dict:
    rows = [*SWARM_DOMAINS, *ca.build_manifest()]
    with_caps = sum(1 for row in rows if "capabilities" in row)
    total = len(rows)
    return {
        "total_agents": total,
        "agents_with_capabilities": with_caps,
        "coverage_pct": round(with_caps / max(total, 1) * 100, 2),
        "summary": jcap.capability_summary(),
    }


# ── Agent mesh ────────────────────────────────────────────────────────────────


@router.get("/mesh/stats")
def mesh_stats() -> dict:
    return mesh.stats()


@router.post("/mesh/rebuild")
def mesh_rebuild() -> dict:
    state = mesh.build_mesh(force=True)
    try:
        from core.swarm_agents import _stamp_mesh_neighbors as stamp_mesh_neighbors

        stamp_mesh_neighbors()
    except Exception:
        pass
    return state


@router.get("/mesh/neighbors/{code}")
def mesh_neighbors(code: str, k: int = 12) -> dict:
    neighbors = mesh.neighbors(code, k=_bounded(k, low=1, high=100))
    return {"code": code, "count": len(neighbors), "neighbors": neighbors}


@router.get("/mesh/reach/{code}")
def mesh_reach(code: str, depth: int = 2) -> dict:
    if not 1 <= depth <= 6:
        raise HTTPException(400, "depth must be 1..6")
    return mesh.reach(code, depth=depth)


@router.get("/mesh/path/{from_code}/{to_code}")
def mesh_path(from_code: str, to_code: str, max_depth: int = 6) -> dict:
    if not 1 <= max_depth <= 10:
        raise HTTPException(400, "max_depth must be 1..10")
    return mesh.path(from_code, to_code, max_depth=max_depth)


@router.get("/mesh/hubs")
def mesh_hubs(top: int = 15) -> dict:
    bounded_top = _bounded(top, low=1, high=100)
    return {"top": bounded_top, "hubs": mesh.hubs(top=bounded_top)}


# ── Full roster ───────────────────────────────────────────────────────────────


def _full_roster():
    from core import full_roster

    return full_roster


@router.get("/roster/manifest")
def roster_manifest() -> dict:
    return _full_roster().manifest()


@router.get("/roster/cohort/{cohort_id}")
def roster_cohort(cohort_id: str, limit: int = 50, offset: int = 0) -> dict:
    roster = _full_roster()
    cohort = roster.cohort_by_id(cohort_id)
    if not cohort:
        raise HTTPException(404, f"unknown cohort '{cohort_id}'")
    bounded_limit = _bounded(limit, low=1, high=500)
    bounded_offset = _bounded(offset, low=0, high=cohort["size"])
    end = min(bounded_offset + bounded_limit, cohort["size"])
    rows = []
    for off in range(bounded_offset, end):
        agent_id = cohort["start"] + off
        rows.append(
            {
                "id": agent_id,
                "code": roster.agent_code(agent_id),
                "team_id": roster.team_id_str(agent_id),
                "legion_id": roster.legion_id_str(agent_id),
            }
        )
    return {
        "cohort": cohort["id"],
        "label": cohort["label"],
        "size": cohort["size"],
        "offset": bounded_offset,
        "returned": len(rows),
        "rows": rows,
    }


@router.get("/roster/resolve/{code}")
def roster_resolve(code: str) -> dict:
    roster = _full_roster()
    try:
        agent_id = roster.id_of_code(code)
    except Exception as exc:
        raise HTTPException(404, f"cannot resolve code '{code}': {exc}") from exc
    location = roster.locate(agent_id)
    cohort = location["cohort"]
    return {
        "code": code,
        "id": agent_id,
        "cohort": cohort["id"],
        "cohort_label": cohort["label"],
        "team": location["team"],
        "team_seat": location["team_seat"],
        "team_id": roster.team_id_str(agent_id),
        "legion": location["legion"],
        "legion_id": roster.legion_id_str(agent_id),
        "is_parliament": agent_id in roster.PARLIAMENT_IDS,
        "is_cohort_hub": agent_id in roster.cohort_hub_ids(cohort, 4),
    }


@router.get("/census")
def census() -> dict:
    """Canonical swarm census, including materialized and full-roster totals."""
    roster = _full_roster()
    return {
        "swarm_agents": len(SWARM_DOMAINS),
        "collection_agents": ca.total_agents(),
        "materialised_agents": len(SWARM_DOMAINS) + ca.total_agents(),
        "full_roster_agents": roster.TOTAL_AGENTS,
        "roster_cohorts": roster.cohort_summary(),
        "total_agents": roster.TOTAL_AGENTS,
        "swarm_categories": _histogram(SWARM_DOMAINS, "category"),
        "swarm_teams": {team_id: len(rows) for team_id, rows in BY_TEAM.items()},
        "swarm_legions": {legion_id: len(rows) for legion_id, rows in BY_LEGION.items()},
        "collection_categories": ca.category_histogram(),
        "cold_storage": cs.stats(),
        "legion_logs": legion.network_stats()["legion_logs"],
        "whispers": whispers.stats(),
        "ledger_total_entries": ledger._ledger.estimated_document_count(),
        "capabilities": jcap.capability_summary(),
    }


def _histogram(rows: list[dict] | tuple[dict, ...], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


# ── Teams / legions / numbering ──────────────────────────────────────────────


@router.get("/teams")
def teams_list() -> dict:
    teams = []
    for team_id, members in BY_TEAM.items():
        leader = members[0] if members else None
        teams.append(
            {
                "team_id": team_id,
                "team_name": leader.get("team_name") if leader else team_id,
                "category": leader.get("category") if leader else None,
                "legion_id": leader.get("legion_id") if leader else None,
                "leader_code": leader.get("agent_code") if leader else None,
                "seats": len(members),
                "members": [
                    {
                        "code": member["agent_code"],
                        "agent": member["agent"],
                        "seat": member.get("team_seat"),
                    }
                    for member in members
                ],
            }
        )
    return {"total_teams": len(teams), "teams": sorted(teams, key=lambda row: row["team_id"])}


@router.get("/teams/{team_id}")
def team_detail(team_id: str) -> dict:
    members = BY_TEAM.get(team_id, [])
    if not members:
        raise HTTPException(404, f"Team '{team_id}' not found")
    return {"team_id": team_id, "seats": len(members), "members": members}


@router.get("/legions")
def legions_list() -> dict:
    rows = []
    for legion_id, members in BY_LEGION.items():
        team_ids = sorted({member["team_id"] for member in members})
        rows.append(
            {
                "legion_id": legion_id,
                "legion_name": members[0].get("legion_name") if members else legion_id,
                "team_ids": team_ids,
                "seats": len(members),
                "agent_code_range": (
                    f"{min(member['agent_code'] for member in members)} – "
                    f"{max(member['agent_code'] for member in members)}"
                    if members
                    else None
                ),
            }
        )
    return {"total_legions": len(rows), "legions": sorted(rows, key=lambda row: row["legion_id"])}


@router.get("/legions/{legion_id}")
def legion_detail(legion_id: str) -> dict:
    members = BY_LEGION.get(legion_id, [])
    if not members:
        raise HTTPException(404, f"Legion '{legion_id}' not found")
    return {
        "legion_id": legion_id,
        "legion_name": members[0].get("legion_name"),
        "team_ids": sorted({member["team_id"] for member in members}),
        "seats": len(members),
        "members": members,
    }


@router.get("/agents/by-number/{number}")
def agent_by_number(number: int) -> dict:
    agent = BY_NUMBER.get(number)
    if agent:
        return {"source": "swarm", "agent": agent}
    for row in ca.build_manifest():
        if row.get("agent_number") == number:
            return {"source": "collection", "agent": row}
    raise HTTPException(404, f"Agent #{number} not found")


# ── Agent ledger ──────────────────────────────────────────────────────────────


@router.get("/ledger/notebook/{agent_code}")
def ledger_notebook(agent_code: str, limit: int = 30) -> dict:
    return {
        "agent_code": agent_code,
        "entries": ledger.notebook(agent_code, _bounded(limit, low=1, high=500)),
    }


@router.get("/ledger/stats")
def ledger_stats(top: int = 15) -> dict:
    return ledger.stats(top=_bounded(top, low=1, high=100))


@router.get("/ledger/build/{build_id}")
def ledger_for_build(build_id: str, limit: int = 200) -> dict:
    return {
        "build_id": build_id,
        "entries": ledger.contributions_for_build(build_id, _bounded(limit, low=1, high=1000)),
    }


# ── Whisper network ──────────────────────────────────────────────────────────


@router.get("/whispers/recent/{recipient_code}")
def whispers_recent(recipient_code: str, limit: int = 20) -> dict:
    return {
        "recipient_code": recipient_code,
        "whispers": whispers.recent(recipient_code, _bounded(limit, low=1, high=200)),
    }


@router.get("/whispers/build/{build_id}")
def whispers_for_build(build_id: str, limit: int = 200) -> dict:
    return {
        "build_id": build_id,
        "whispers": whispers.for_build(build_id, _bounded(limit, low=1, high=500)),
    }


@router.get("/whispers/stats")
def whispers_stats() -> dict:
    return whispers.stats()


# ── Platoons ─────────────────────────────────────────────────────────────────


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
        build_id=req.build_id,
        phase_id=req.phase_id,
        game_ctx=req.game_ctx,
        rotation_idx=max(req.rotation_idx, 0),
        prev_handoff=req.prev_handoff,
        rounds=_bounded(req.rounds, low=1, high=20),
        size=_bounded(req.size, low=1, high=100),
        persist=req.persist,
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
        build_id=req.build_id,
        batch_num=max(req.batch_num, 1),
        game_ctx=req.game_ctx,
        phase_ids=req.phase_ids,
        rounds=_bounded(req.rounds, low=1, high=20),
        size=_bounded(req.size, low=1, high=100),
    )


@router.get("/platoons/build/{build_id}")
def platoons_for_build(build_id: str, limit: int = 200) -> dict:
    return {
        "build_id": build_id,
        "platoons": platoons_mod.platoons_for_build(build_id, _bounded(limit, low=1, high=1000)),
    }


@router.get("/platoons/coverage/{build_id}")
def platoons_coverage(build_id: str) -> dict:
    return platoons_mod.coverage_stats(build_id)


@router.get("/platoons/participation/{build_id}")
def platoons_participation(build_id: str, limit: int = 500) -> dict:
    return {
        "build_id": build_id,
        "rows": platoons_mod.participation_rows(build_id, _bounded(limit, low=1, high=2000)),
    }


class SweepReq(BaseModel):
    build_id: str
    game_ctx: dict[str, Any] = Field(default_factory=dict)


@router.post("/platoons/sweep")
def platoons_sweep(req: SweepReq) -> dict:
    return platoons_mod.force_participation_sweep(req.build_id, req.game_ctx)
