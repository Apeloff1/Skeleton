"""
routes/galaxy_studio_code_library.py — Code-library sub-router.

Extracted from routes/galaxy_studio.py (Phase-3 decomposition, Feb 2026).
These endpoints are pure read/search over the ``game_code_library`` Mongo
collection in content_db — they don't touch any of the in-memory build
state, so they're a safe extraction target.

Note about seeding: the original ``_ensure_code_library_seeded`` lives in
the parent module because it has deep imports we don't want to duplicate.
We forward to it via a lazy import inside the request handler so the
sub-router never imports the parent at module-load time (no circular).
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["galaxy-studio"])


@router.get("/code-library/stats")
async def code_library_stats() -> dict:
    """Total snippets + virtual line count + per-axis breakdowns.
    Kicks off the seeder on first call if the collection is empty."""
    try:
        from core.databases import content_db as _cdb
        # Fire-and-forget seeder if collection empty.
        count_check = await _cdb.game_code_library.count_documents({}, limit=1)
        if count_check == 0:
            import asyncio
            from routes.galaxy_studio import _ensure_code_library_seeded  # lazy
            asyncio.create_task(_ensure_code_library_seeded())
            return {
                "status": "seeding",
                "message": "Code library seeding started in background. Retry in ~30s.",
                "total_snippets": 0,
                "virtual_line_count": 0,
            }

        agg = await _cdb.game_code_library.aggregate([
            {"$group": {
                "_id": None,
                "total_virtual_lines": {"$sum": "$virtual_line_count"},
                "docs": {"$sum": 1},
            }}
        ]).to_list(1)
        base = agg[0] if agg else {"docs": 0, "total_virtual_lines": 0}

        async def _axis(field: str) -> list[dict]:
            try:
                rows = await _cdb.game_code_library.aggregate([
                    {"$group": {"_id": f"${field}", "count": {"$sum": 1}, "lines": {"$sum": "$virtual_line_count"}}},
                    {"$sort": {"lines": -1}},
                    {"$limit": 20},
                ]).to_list(20)
                return [{"key": r["_id"], "snippets": r["count"], "virtual_lines": r["lines"]} for r in rows]
            except Exception:
                return []

        return {
            "status": "ready",
            "total_snippets": base.get("docs", 0),
            "virtual_line_count": base.get("total_virtual_lines", 0),
            "virtual_line_count_human": f"{base.get('total_virtual_lines', 0):,}",
            "per_category": await _axis("category"),
            "per_genre": await _axis("genre"),
            "per_era": await _axis("era"),
            "per_language": await _axis("language"),
            "collection": "game_code_library",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)[:200], "total_snippets": 0, "virtual_line_count": 0}


@router.post("/code-library/search")
async def code_library_search(req: dict) -> dict:
    """Agent-facing: returns up to 100 snippets matching
    category/era/genre/language/keyword/agent_id filters."""
    try:
        from core.databases import content_db as _cdb
        q: dict = {}
        for k in ("category", "era", "genre", "language", "engine"):
            v = req.get(k)
            if v:
                q[k] = v
        kw = req.get("keyword")
        if kw:
            q["keywords"] = kw
        agent_id = req.get("agent_id")
        if agent_id:
            q["agent_ids"] = agent_id
        limit = max(1, min(100, int(req.get("limit", 20))))
        skip = max(0, int(req.get("skip", 0)))
        cursor = _cdb.game_code_library.find(q, {"_id": 0}).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        total = await _cdb.game_code_library.count_documents(q)
        return {
            "query": q,
            "total": total,
            "returned": len(docs),
            "skip": skip,
            "limit": limit,
            "snippets": docs,
        }
    except Exception as e:
        return {"query": req, "total": 0, "returned": 0, "error": str(e)[:200], "snippets": []}


__all__ = ["router"]
