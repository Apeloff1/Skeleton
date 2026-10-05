"""
routes/galaxy_studio_mega_dbs.py — Mega-DB & DB-status sub-router.

Extracted from routes/galaxy_studio.py (Phase-4 decomposition, Feb 2026).
List/query/seed the 200-collection mega game-asset store + cross-DB
collection status + bootstrap-all. Read-only against content_db plus a
background seeder kick-off; no in-memory build state.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["galaxy-studio"])


@router.get("/mega-dbs/list")
async def list_mega_dbs():
    """List all 200 mega game-asset collections with their category + current doc count."""
    try:
        from core.databases import content_db as _cdb
        from seeds.mega_game_db_seed import MEGA_COLLECTIONS, MEGA_CATEGORIES, TOTAL_MEGA_COLLECTIONS
        out = []
        for name, cat in MEGA_COLLECTIONS:
            try:
                # mega-collections are routed to content_db, not core_db.
                c = await _cdb[name].count_documents({}, limit=5000)
            except Exception:
                c = 0
            out.append({"name": name, "category": cat, "docs": c, "ready": c > 0})
        by_cat: dict[str, int] = {}
        for row in out:
            by_cat.setdefault(row["category"], 0)
            by_cat[row["category"]] += row["docs"]
        return {
            "total_collections":    TOTAL_MEGA_COLLECTIONS,
            "total_docs":           sum(r["docs"] for r in out),
            "ready_collections":    sum(1 for r in out if r["ready"]),
            "categories":           list(MEGA_CATEGORIES.keys()),
            "docs_per_category":    by_cat,
            "collections":          out,
        }
    except Exception as e:
        return {"error": str(e)[:200], "total_collections": 0}


@router.post("/mega-dbs/query")
async def query_mega_db(req: dict):
    """Unified agent-query endpoint across all 200 mega collections.
    Body: {collection: str, category?: str, era?: str, genre?: str, keyword?: str, tag?: str,
           agent_id?: str, rarity?: str, limit?: int, skip?: int}"""
    try:
        from core.databases import content_db as _cdb
        from seeds.mega_game_db_seed import MEGA_COLLECTIONS
        coll_name = req.get("collection")
        if not coll_name:
            return {"error": "collection field is required", "results": []}
        valid_names = {n for n, _ in MEGA_COLLECTIONS}
        if coll_name not in valid_names:
            return {"error": f"Unknown mega collection '{coll_name}'. Use /mega-dbs/list.", "results": []}
        q: dict = {}
        for k in ("category", "era", "genre"):
            v = req.get(k)
            if v: q[k] = v
        if req.get("keyword"):  q["keywords"]  = req["keyword"]
        if req.get("tag"):      q["tags"]      = req["tag"]
        if req.get("agent_id"): q["agent_ids"] = req["agent_id"]
        if req.get("rarity"):   q["params.rarity_tier"] = req["rarity"]
        limit = max(1, min(100, int(req.get("limit", 20))))
        skip  = max(0, int(req.get("skip",  0)))
        cursor  = _cdb[coll_name].find(q, {"_id": 0}).skip(skip).limit(limit)
        results = await cursor.to_list(length=limit)
        total   = await _cdb[coll_name].count_documents(q)
        return {
            "collection": coll_name, "query": q, "total": total,
            "returned":   len(results), "skip": skip, "limit": limit,
            "results":    results,
        }
    except Exception as e:
        return {"error": str(e)[:200], "results": []}


@router.post("/mega-dbs/seed")
async def trigger_mega_seed():
    """Triggers the 200-collection mega seeder in the background. Idempotent."""
    try:
        import asyncio as _aio
        from core.databases import content_db as _cdb
        from seeds.mega_game_db_seed import seed_all_mega_dbs, TOTAL_MEGA_COLLECTIONS
        _aio.create_task(seed_all_mega_dbs(_cdb))
        return {
            "status":                  "seeding_started",
            "total_collections_planned": TOTAL_MEGA_COLLECTIONS,
            "message":                  "Mega DB seed kicked off in background. Poll /mega-dbs/list for progress.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


@router.get("/db-status")
async def db_fill_status():
    """Report document count for every collection across core_db AND content_db.
    Useful for the frontend to verify that every database the agents reference is filled."""
    try:
        from core.databases import core_db as _db, content_db as _cdb
        rows: list[dict] = []
        core_names = await _db.list_collection_names()
        for n in core_names:
            try:
                c = await _db[n].count_documents({})
            except Exception:
                c = -1
            rows.append({"name": n, "db": "core",    "count": c, "empty": c == 0})
        content_names = await _cdb.list_collection_names()
        for n in content_names:
            try:
                c = await _cdb[n].count_documents({})
            except Exception:
                c = -1
            rows.append({"name": n, "db": "content", "count": c, "empty": c == 0})
        rows.sort(key=lambda r: (-r["count"], r["name"]))
        total = sum(r["count"] for r in rows if r["count"] > 0)
        empty = [r["name"] for r in rows if r["count"] == 0]
        return {
            "total_collections":   len(rows),
            "total_docs":          total,
            "core_collections":    len(core_names),
            "content_collections": len(content_names),
            "empty_collections":   empty,
            "collections":         rows,
        }
    except Exception as e:
        return {"error": str(e)[:200], "total_collections": 0}


@router.post("/bootstrap-dbs")
async def bootstrap_all_dbs():
    """Idempotent bootstrap of any missing/empty agent-referenced collections.
    Seeds tutorial_progress and bootstraps galaxy_vault / jeeves_builds / galaxy_build_archive."""
    try:
        from services.database import db as _db
        from core.databases import content_db as _cdb
        from seeds.bootstrap_seeder import bootstrap_all
        code_lib_count = await _cdb.game_code_library.count_documents({}, limit=1)
        if code_lib_count == 0:
            try:
                from seeds.game_code_library_seed import seed_game_code_library
                await seed_game_code_library(_cdb)
            except Exception as e:
                print(f"[bootstrap] code_library seed failed: {e}")
        result = await bootstrap_all(_db)
        return result
    except Exception as e:
        return {"error": str(e)[:200]}
