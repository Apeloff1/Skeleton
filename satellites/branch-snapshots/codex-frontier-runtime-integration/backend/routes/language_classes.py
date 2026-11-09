"""Language Classes API — 451+ programming languages with full curriculum"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent.parent / '.env')

router = APIRouter(prefix="/api/languages-academy", tags=["languages-academy"])
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}


@router.get("/all")
async def get_all_languages(category: Optional[str] = None, difficulty: Optional[str] = None, limit: int = Query(100, le=500), skip: int = Query(0, ge=0)):
    """Get all language classes with filtering and pagination."""
    q = {}
    if category: q["category"] = category
    if difficulty: q["difficulty"] = difficulty
    langs = await _db.language_classes.find(q, {**PROJ, "chapters": 0}).skip(skip).limit(limit).to_list(limit)
    total = await _db.language_classes.count_documents(q)
    return {"languages": langs, "total": total, "showing": len(langs), "skip": skip}


@router.get("/stats")
async def get_language_stats():
    """Get language statistics by category and difficulty."""
    pipeline = [{"$group": {"_id": {"category": "$category", "difficulty": "$difficulty"}, "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    results = await _db.language_classes.aggregate(pipeline).to_list(100)
    total = await _db.language_classes.count_documents({})
    by_cat = {}
    by_diff = {}
    for r in results:
        cat = r["_id"]["category"]
        diff = r["_id"]["difficulty"]
        by_cat[cat] = by_cat.get(cat, 0) + r["count"]
        by_diff[diff] = by_diff.get(diff, 0) + r["count"]
    executable = await _db.language_classes.count_documents({"executable_in_playground": True})
    return {"total": total, "by_category": by_cat, "by_difficulty": by_diff, "executable_in_playground": executable}


@router.get("/search")
async def search_languages(q: str = Query(...), limit: int = Query(20, le=50)):
    """Search languages by name, paradigm, or use cases."""
    results = await _db.language_classes.find(
        {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"paradigm": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"creator": {"$regex": q, "$options": "i"}},
        ]},
        {**PROJ, "chapters": 0}
    ).limit(limit).to_list(limit)
    return {"results": results, "total": len(results), "query": q}


@router.get("/categories")
async def get_language_categories():
    """Get all language categories with counts."""
    pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    results = await _db.language_classes.aggregate(pipeline).to_list(20)
    return {"categories": [{"category": r["_id"], "count": r["count"]} for r in results]}


@router.get("/executable")
async def get_executable_languages():
    """Get languages that can be executed in the playground."""
    langs = await _db.language_classes.find({"executable_in_playground": True}, {**PROJ, "chapters": 0}).to_list(50)
    return {"languages": langs, "total": len(langs)}


@router.get("/{lang_id}")
async def get_language_detail(lang_id: str):
    """Get full language class with curriculum."""
    lang = await _db.language_classes.find_one({"id": lang_id}, PROJ)
    if not lang:
        # Try by slug
        lang = await _db.language_classes.find_one({"slug": lang_id}, PROJ)
    if not lang:
        raise HTTPException(404, f"Language '{lang_id}' not found")
    return {"language": lang}
