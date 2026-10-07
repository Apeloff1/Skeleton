"""Coding Dictionary API — syntax refs, patterns, algorithms, prompts, courses"""
from fastapi import APIRouter, Query
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent.parent / '.env')

router = APIRouter(prefix="/api/dictionary", tags=["dictionary"])
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}


@router.get("/browse")
async def browse_dictionary(type: Optional[str] = None, category: Optional[str] = None, language: Optional[str] = None, difficulty: Optional[str] = None, limit: int = Query(50, le=200), skip: int = Query(0, ge=0)):
    """Browse the coding dictionary with filters."""
    q = {}
    if type: q["type"] = type
    if category: q["category"] = category
    if language: q["language"] = language
    if difficulty: q["difficulty"] = difficulty
    entries = await _db.coding_dictionary.find(q, PROJ).skip(skip).limit(limit).to_list(limit)
    total = await _db.coding_dictionary.count_documents(q)
    return {"entries": entries, "total": total, "showing": len(entries), "skip": skip}


@router.get("/stats")
async def dictionary_stats():
    """Get dictionary statistics."""
    pipeline = [{"$group": {"_id": "$type", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    by_type = await _db.coding_dictionary.aggregate(pipeline).to_list(20)
    pipeline2 = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    by_cat = await _db.coding_dictionary.aggregate(pipeline2).to_list(20)
    total = await _db.coding_dictionary.count_documents({})
    return {
        "total": total,
        "by_type": {r["_id"]: r["count"] for r in by_type},
        "by_category": {r["_id"]: r["count"] for r in by_cat},
    }


@router.get("/search")
async def search_dictionary(q: str = Query(...), limit: int = Query(20, le=50)):
    """Search the dictionary by name, concept, or code."""
    results = await _db.coding_dictionary.find(
        {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"concept_name": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"code": {"$regex": q, "$options": "i"}},
            {"language": {"$regex": q, "$options": "i"}},
            {"prompt_template": {"$regex": q, "$options": "i"}},
            {"topic": {"$regex": q, "$options": "i"}},
        ]},
        PROJ
    ).limit(limit).to_list(limit)
    return {"results": results, "total": len(results), "query": q}


@router.get("/syntax/{concept}")
async def get_syntax_reference(concept: str, language: Optional[str] = None):
    """Get syntax reference for a concept, optionally filtered by language."""
    q = {"type": "syntax_reference", "concept": concept}
    if language: q["language"] = language
    entries = await _db.coding_dictionary.find(q, PROJ).to_list(50)
    return {"concept": concept, "references": entries, "total": len(entries)}


@router.get("/patterns")
async def get_design_patterns(pattern_category: Optional[str] = None):
    """Get all design patterns."""
    q = {"type": "design_pattern"}
    if pattern_category: q["pattern_category"] = pattern_category
    entries = await _db.coding_dictionary.find(q, PROJ).to_list(50)
    return {"patterns": entries, "total": len(entries)}


@router.get("/algorithms")
async def get_algorithms(algo_category: Optional[str] = None):
    """Get all algorithms."""
    q = {"type": "algorithm"}
    if algo_category: q["algo_category"] = algo_category
    entries = await _db.coding_dictionary.find(q, PROJ).to_list(50)
    return {"algorithms": entries, "total": len(entries)}


@router.get("/prompts")
async def get_ai_prompts(prompt_category: Optional[str] = None):
    """Get AI coding prompts."""
    q = {"type": "ai_prompt"}
    if prompt_category: q["prompt_category"] = prompt_category
    entries = await _db.coding_dictionary.find(q, PROJ).to_list(100)
    return {"prompts": entries, "total": len(entries)}


@router.get("/courses")
async def get_courses(domain: Optional[str] = None, difficulty: Optional[str] = None):
    """Get all courses."""
    q = {"type": "course"}
    if domain: q["domain"] = domain
    if difficulty: q["difficulty"] = difficulty
    entries = await _db.coding_dictionary.find(q, PROJ).to_list(50)
    return {"courses": entries, "total": len(entries)}



# ═══════════════════════════════════════════════════════════════
# ROSETTA STONE — Cross-language syntax comparison (3,690 entries)
# ═══════════════════════════════════════════════════════════════

@router.get("/rosetta")
async def browse_rosetta(concept: Optional[str] = None, language: Optional[str] = None, limit: int = Query(50, le=200), skip: int = Query(0, ge=0)):
    """Browse the Rosetta Stone — compare syntax across languages."""
    q = {}
    if concept: q["concept"] = concept
    if language: q["language"] = language
    entries = await _db.rosetta_stone.find(q, PROJ).skip(skip).limit(limit).to_list(limit)
    total = await _db.rosetta_stone.count_documents(q)
    return {"entries": entries, "total": total, "showing": len(entries), "skip": skip}


@router.get("/rosetta/concepts")
async def rosetta_concepts():
    """Get all Rosetta Stone concept categories."""
    pipeline = [{"$group": {"_id": "$concept", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
    results = await _db.rosetta_stone.aggregate(pipeline).to_list(2000)
    total = await _db.rosetta_stone.count_documents({})
    return {"concepts": [{"concept": r["_id"], "languages": r["count"]} for r in results], "total_entries": total}


@router.get("/rosetta/{concept_name}")
async def rosetta_concept(concept_name: str):
    """Get a specific concept across ALL languages."""
    entries = await _db.rosetta_stone.find({"concept": concept_name}, PROJ).to_list(50)
    return {"concept": concept_name, "languages": entries, "total": len(entries)}


# ═══════════════════════════════════════════════════════════════
# HYPERION CLASS DICTIONARY — Programming term encyclopedia (194 terms)
# ═══════════════════════════════════════════════════════════════

@router.get("/hyperion")
async def browse_hyperion(category: Optional[str] = None, limit: int = Query(50, le=200), skip: int = Query(0, ge=0)):
    """Browse the Hyperion Class Dictionary."""
    q = {}
    if category: q["category"] = category
    entries = await _db.hyperion_dictionary.find(q, PROJ).skip(skip).limit(limit).to_list(limit)
    total = await _db.hyperion_dictionary.count_documents(q)
    return {"entries": entries, "total": total, "showing": len(entries), "skip": skip}


@router.get("/hyperion/search")
async def search_hyperion(q: str = Query(...), limit: int = Query(20, le=50)):
    """Search the Hyperion dictionary."""
    results = await _db.hyperion_dictionary.find(
        {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"definition": {"$regex": q, "$options": "i"}},
            {"term": {"$regex": q, "$options": "i"}},
        ]}, PROJ
    ).limit(limit).to_list(limit)
    return {"results": results, "total": len(results), "query": q}


@router.get("/hyperion/{term}")
async def get_hyperion_term(term: str):
    """Get a specific Hyperion dictionary term."""
    entry = await _db.hyperion_dictionary.find_one({"term": term}, PROJ)
    if not entry:
        entry = await _db.hyperion_dictionary.find_one({"id": f"hyp_{term}"}, PROJ)
    return {"term": entry} if entry else {"error": f"Term '{term}' not found"}
