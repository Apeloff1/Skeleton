"""
╔════════════════════════════════════════════════════════════════════════╗
║  SWARM HUB — Public API for hyperscale swarm & compressed vault        ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Endpoints (all prefixed with /api/galaxy-studio/swarm/*):             ║
║                                                                        ║
║    GET  /agents                       → list all 200 swarm agents     ║
║    GET  /agents/categories            → category histogram            ║
║    GET  /agents/{agent_id}            → single agent detail           ║
║                                                                        ║
║    GET  /micro-dbs                    → manifest list (shards)        ║
║    GET  /micro-dbs/stats              → total rows, size, ratio       ║
║    GET  /micro-dbs/{shard}/sample     → sample rows from a shard      ║
║    GET  /micro-dbs/{shard}/query      → paginated rows (limit/offset) ║
║    POST /micro-dbs/seed               → (re)seed shards on demand     ║
║                                                                        ║
║    POST /discourse/simulate           → run a discourse round         ║
║    GET  /discourse/latest             → latest N discourse logs       ║
║    GET  /discourse/build/{build_id}   → discourse for a specific build║
║    GET  /discourse/stats              → counts                        ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.swarm_agents import SWARM_DOMAINS, BY_ID, BY_CATEGORY, find_relevant, pick_balanced
from core.compressed_vault import (
    list_shards,
    vault_stats,
    read_shard,
    sample_shard,
    get_shard_entry,
)
from core.discourse_engine import (
    simulate,
    get_for_build,
    latest as discourse_latest,
    discourse_stats,
)

router = APIRouter(prefix="/api/galaxy-studio/swarm", tags=["swarm-hub"])


# ── Agents ──────────────────────────────────────────────────────────────
@router.get("/agents")
def list_agents(category: str | None = None, q: str | None = None) -> dict:
    agents = SWARM_DOMAINS
    if category:
        agents = [a for a in agents if a["category"] == category]
    if q:
        ql = q.lower()
        agents = [
            a for a in agents
            if ql in a["id"] or ql in a["domain"].lower() or ql in a["agent"].lower()
            or any(ql in kw for kw in a["expertise"])
        ]
    return {"total": len(agents), "agents": agents}


@router.get("/agents/categories")
def agent_categories() -> dict:
    return {
        "total_agents": len(SWARM_DOMAINS),
        "categories": [
            {"category": cat, "count": len(bucket), "ids": [a["id"] for a in bucket]}
            for cat, bucket in BY_CATEGORY.items()
        ],
    }


@router.get("/agents/{agent_id}")
def agent_detail(agent_id: str) -> dict:
    a = BY_ID.get(agent_id)
    if not a:
        raise HTTPException(404, f"Unknown agent '{agent_id}'")
    shard = get_shard_entry(agent_id)
    return {"agent": a, "shard": shard}


@router.get("/agents/relevant/search")
def relevant_agents(keywords: str = Query(..., description="comma or space separated"), limit: int = 6) -> dict:
    tokens = [t.strip() for t in keywords.replace(",", " ").split() if t.strip()]
    matches = find_relevant(tokens, limit=limit)
    return {"query": tokens, "matches": matches}


# ── Micro DBs (compressed vault) ───────────────────────────────────────
@router.get("/micro-dbs")
def list_micro_dbs(category: str | None = None) -> dict:
    shards = list_shards()
    if category:
        allowed_ids = {a["id"] for a in SWARM_DOMAINS if a["category"] == category}
        shards = [s for s in shards if s["name"] in allowed_ids]
    return {"total": len(shards), "shards": shards}


@router.get("/micro-dbs/stats")
def micro_db_stats() -> dict:
    s = vault_stats()
    # Add MB aliases for frontend ergonomics
    s["compressed_mb"] = round(s.get("total_compressed_bytes", 0) / 1024 / 1024, 2)
    s["raw_mb"] = round(s.get("total_raw_bytes", 0) / 1024 / 1024, 2)
    return s


@router.get("/micro-dbs/{shard}/sample")
def micro_db_sample(shard: str, k: int = 5) -> dict:
    if not get_shard_entry(shard):
        raise HTTPException(404, f"Shard '{shard}' not found (run seed first)")
    return {"shard": shard, "rows": sample_shard(shard, k=min(max(k, 1), 50))}


@router.get("/micro-dbs/{shard}/query")
def micro_db_query(shard: str, limit: int = 50, offset: int = 0) -> dict:
    if not get_shard_entry(shard):
        raise HTTPException(404, f"Shard '{shard}' not found")
    rows = read_shard(shard, limit=min(max(limit, 1), 500), offset=max(offset, 0))
    return {"shard": shard, "limit": limit, "offset": offset, "count": len(rows), "rows": rows}


class SeedReq(BaseModel):
    target_multiplier: float = 1.0
    force: bool = False
    subset: list[str] | None = None


@router.post("/micro-dbs/seed")
def micro_db_seed(req: SeedReq) -> dict:
    # Heavy operation – guard against accidental thermonuclear seeds.
    if req.target_multiplier > 200:
        raise HTTPException(400, "target_multiplier capped at 200 for safety")
    # Lazy import to keep router boot light
    from seeds.hyperscale_micro_dbs import seed_all
    return seed_all(
        target_multiplier=req.target_multiplier,
        force=req.force,
        subset=req.subset,
    )


# ── Discourse ──────────────────────────────────────────────────────────
class DiscourseReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    phase: str = Field(..., min_length=1)
    game_ctx: dict[str, Any] = Field(default_factory=dict)
    rounds: int = 3
    persist: bool = True


@router.post("/discourse/simulate")
def discourse_simulate(req: DiscourseReq) -> dict:
    if req.rounds < 1 or req.rounds > 10:
        raise HTTPException(400, "rounds must be between 1 and 10")
    return simulate(
        build_id=req.build_id,
        phase=req.phase,
        game_ctx=req.game_ctx,
        rounds=req.rounds,
        persist=req.persist,
    )


@router.get("/discourse/latest")
def discourse_latest_endpoint(limit: int = 10) -> dict:
    return {"logs": discourse_latest(min(max(limit, 1), 100))}


@router.get("/discourse/build/{build_id}")
def discourse_for_build(build_id: str, phase: str | None = None, limit: int = 20) -> dict:
    return {"build_id": build_id, "phase": phase, "logs": get_for_build(build_id, phase, limit)}


@router.get("/discourse/stats")
def discourse_stats_endpoint() -> dict:
    return discourse_stats()


# ── Unified overview ───────────────────────────────────────────────────
@router.get("/overview")
def overview() -> dict:
    stats = vault_stats()
    return {
        "total_agents": len(SWARM_DOMAINS),
        "categories": len(BY_CATEGORY),
        "total_shards": stats["shard_count"],
        "total_rows": stats["total_rows"],
        "compressed_mb": round(stats["total_compressed_bytes"] / 1024 / 1024, 2),
        "raw_mb": round(stats["total_raw_bytes"] / 1024 / 1024, 2),
        "avg_compression_ratio": stats["avg_compression_ratio"],
        "discourse_logs": discourse_stats()["total_logs"],
    }
