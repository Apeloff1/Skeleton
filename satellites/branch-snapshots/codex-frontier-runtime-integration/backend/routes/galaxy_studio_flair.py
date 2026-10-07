"""
routes/galaxy_studio_flair.py — Flair sub-router.

Extracted from routes/galaxy_studio.py (Phase-4 decomposition, Feb 2026).
Pure read/seed endpoints over the ``unique_flair`` Mongo collection in
content_db. No in-memory build state touched → safe extraction target.

The parent module wires this in via ``router.include_router(...)`` so the
public paths (``/api/galaxy-studio/flair/*``) remain unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["galaxy-studio"])


@router.get("/flair/stats")
async def flair_stats():
    """Stats for the unique_flair collection: total, per-category, per-rarity."""
    try:
        from core.databases import content_db as _cdb
        total = await _cdb.unique_flair.count_documents({})

        async def _axis(field: str):
            try:
                rows = await _cdb.unique_flair.aggregate([
                    {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 30},
                ]).to_list(30)
                return [{"key": r["_id"], "count": r["count"]} for r in rows]
            except Exception:
                return []

        return {
            "total_flair": total,
            "per_category": await _axis("category"),
            "per_rarity":   await _axis("rarity"),
            "per_mood":     await _axis("mood"),
            "per_era":      await _axis("era"),
        }
    except Exception as e:
        return {"total_flair": 0, "error": str(e)[:200]}


@router.get("/flair/random")
async def flair_random(
    category: str = None,
    rarity:   str = None,
    era:      str = None,
    genre:    str = None,
    count:    int = 5,
):
    """Pull N random flair entries matching optional filters. Agents call this for creative fuel."""
    try:
        from core.databases import content_db as _cdb
        pipeline: list[dict] = []
        match: dict = {}
        if category: match["category"] = category
        if rarity:   match["rarity"]   = rarity
        if era:      match["era"]      = era
        if genre:    match["genre"]    = genre
        if match:    pipeline.append({"$match": match})
        n = max(1, min(50, count))
        pipeline.append({"$sample": {"size": n}})
        pipeline.append({"$project": {"_id": 0}})
        docs = await _cdb.unique_flair.aggregate(pipeline).to_list(n)
        return {"count": len(docs), "filters": match, "flair": docs}
    except Exception as e:
        return {"count": 0, "error": str(e)[:200], "flair": []}


@router.post("/flair/seed")
async def trigger_flair_seed():
    """Idempotent — seeds/tops-up the 50k unique_flair collection in background."""
    try:
        import asyncio as _aio
        from services.database import db as _db
        from seeds.unique_flair_seed import seed_unique_flair, TOTAL_FLAIR
        _aio.create_task(seed_unique_flair(_db))
        return {
            "status": "seeding_started",
            "target_flair": TOTAL_FLAIR,
            "message": "50,000 unique flair entries seeding in background.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}
