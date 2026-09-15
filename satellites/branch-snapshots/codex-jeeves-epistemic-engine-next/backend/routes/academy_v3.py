"""
Academy Routes v3.0 — MongoDB-Backed
All data served from pre-seeded MongoDB collections.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent.parent / '.env')

router = APIRouter(prefix="/api/academy", tags=["academy"])

# Use centralized DB handles — reading_library + bugfix_library live in
# content_db (regenerable, not migrated). User/track data stays on core.
from core.databases import core_db as _db, content_db as _cdb

PROJECTION = {"_id": 0}


# ═══════════════════════════════════════════════════════════════
# TRACKS (Language Learning)
# ═══════════════════════════════════════════════════════════════

@router.get("/tracks")
async def get_all_tracks(
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=500)
):
    """Get all language/gamedev tracks from MongoDB with pagination."""
    query = {}
    if category:
        regex = {"$regex": category, "$options": "i"}
        query["$or"] = [{"name": regex}, {"description": regex}, {"category": regex}]
        
    skip = (page - 1) * limit
    total_docs = await _db.academy_tracks.count_documents(query)
    
    tracks = await _db.academy_tracks.find(query, {**PROJECTION, "modules": 0}).skip(skip).limit(limit).to_list(limit)
    
    return {
        "tracks": tracks,
        "total_count": total_docs,
        "page": page,
        "pages": (total_docs + limit - 1) // limit,
        "total_hours": sum(t.get("total_hours", 0) for t in tracks),
    }


@router.get("/track/{track_id}")
async def get_track_detail(track_id: str):
    """Get full track with all modules and lessons."""
    track = await _db.academy_tracks.find_one({"id": track_id}, PROJECTION)
    if not track:
        raise HTTPException(404, f"Track '{track_id}' not found")
    return {
        "track": track,
        "total_modules": len(track.get("modules", [])),
        "total_lessons": track.get("total_lessons", 0),
        "total_exercises": track.get("total_exercises", 0),
    }


@router.get("/track/{track_id}/module/{module_id}")
async def get_module_content(track_id: str, module_id: str):
    """Get a specific module from a track."""
    track = await _db.academy_tracks.find_one({"id": track_id}, PROJECTION)
    if not track:
        raise HTTPException(404, f"Track '{track_id}' not found")
    module = next((m for m in track.get("modules", []) if m.get("id") == module_id), None)
    if not module:
        raise HTTPException(404, f"Module '{module_id}' not found in track '{track_id}'")
    return {"module": module, "track_name": track.get("name", "")}


@router.get("/track/{track_id}/module/{module_id}/lesson/{lesson_id}")
async def get_lesson(track_id: str, module_id: str, lesson_id: str):
    """Get a specific lesson."""
    track = await _db.academy_tracks.find_one({"id": track_id}, PROJECTION)
    if not track:
        raise HTTPException(404, f"Track '{track_id}' not found")
    for module in track.get("modules", []):
        if module.get("id") == module_id:
            lesson = next((l for l in module.get("lessons", []) if l.get("id") == lesson_id), None)
            if lesson:
                return {"lesson": lesson, "module_name": module.get("name", ""), "track_name": track.get("name", "")}
    raise HTTPException(404, f"Lesson '{lesson_id}' not found")


# ═══════════════════════════════════════════════════════════════
# SUBJECT ACADEMIES (Math, Physics, CS, Game Dev, etc.)
# ═══════════════════════════════════════════════════════════════

@router.get("/subjects")
async def get_all_subjects(
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=500),
    category: str = None
):
    """Get all subject academy tracks with pagination."""
    query = {}
    if category:
        regex = {"$regex": category, "$options": "i"}
        query["$or"] = [{"title": regex}, {"content": regex}, {"category": regex}]
    skip = (page - 1) * limit
    total_docs = await _db.academy_subjects.count_documents(query)
    subjects = await _db.academy_subjects.find(query, {**PROJECTION, "modules": 0}).skip(skip).limit(limit).to_list(limit)
    return {
        "subjects": subjects, 
        "total_count": total_docs,
        "page": page,
        "pages": (total_docs + limit - 1) // limit
    }


@router.get("/subject/{subject_id}")
async def get_subject_detail(subject_id: str):
    """Get full subject academy with modules."""
    subject = await _db.academy_subjects.find_one({"id": subject_id}, PROJECTION)
    if not subject:
        raise HTTPException(404, f"Subject '{subject_id}' not found")
    return {"subject": subject}


# ═══════════════════════════════════════════════════════════════
# EXERCISES, PROJECTS, ASSESSMENTS
# ═══════════════════════════════════════════════════════════════

@router.get("/exercises")
async def get_exercises(
    track_id: Optional[str] = None, 
    module_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=500)
):
    query = {}
    if track_id: query["track_id"] = track_id
    if module_id: query["module_id"] = module_id
    skip = (page - 1) * limit
    total_docs = await _db.exercises.count_documents(query)
    items = await _db.exercises.find(query, PROJECTION).skip(skip).limit(limit).to_list(limit)
    return {"exercises": items, "total_count": total_docs, "page": page, "pages": (total_docs + limit - 1) // limit}


@router.get("/exercise/{exercise_id}")
async def get_exercise(exercise_id: str):
    """Get a specific exercise with solution."""
    ex = await _db.exercises.find_one({"id": exercise_id}, PROJECTION)
    if not ex:
        raise HTTPException(404, f"Exercise '{exercise_id}' not found")
    return {"exercise": ex}


@router.get("/projects")
async def get_projects(
    track_id: Optional[str] = None, 
    module_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=500)
):
    query = {}
    if track_id: query["track_id"] = track_id
    if module_id: query["module_id"] = module_id
    skip = (page - 1) * limit
    total_docs = await _db.projects.count_documents(query)
    items = await _db.projects.find(query, PROJECTION).skip(skip).limit(limit).to_list(limit)
    return {"projects": items, "total_count": total_docs, "page": page, "pages": (total_docs + limit - 1) // limit}


@router.get("/project/{project_id}")
async def get_project(project_id: str):
    """Get a specific project."""
    proj = await _db.projects.find_one({"id": project_id}, PROJECTION)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return {"project": proj}


@router.get("/assessments")
async def get_assessments(
    track_id: Optional[str] = None, 
    module_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=500)
):
    query = {}
    if track_id: query["track_id"] = track_id
    if module_id: query["module_id"] = module_id
    skip = (page - 1) * limit
    total_docs = await _db.assessments.count_documents(query)
    items = await _db.assessments.find(query, PROJECTION).skip(skip).limit(limit).to_list(limit)
    return {"assessments": items, "total_count": total_docs, "page": page, "pages": (total_docs + limit - 1) // limit}


@router.get("/assessment/{assessment_id}")
async def get_assessment(assessment_id: str):
    """Get a specific assessment."""
    assess = await _db.assessments.find_one({"id": assessment_id}, PROJECTION)
    if not assess:
        raise HTTPException(404, f"Assessment '{assessment_id}' not found")
    return {"assessment": assess}


# ═══════════════════════════════════════════════════════════════
# ALGORITHM CHALLENGES (Interview Prep)
# ═══════════════════════════════════════════════════════════════

@router.get("/challenges")
async def get_challenges(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=500)
):
    query = {}
    if category: query["category"] = category
    if difficulty: query["difficulty"] = difficulty
    skip = (page - 1) * limit
    total_docs = await _db.algo_challenges.count_documents(query)
    challenges = await _db.algo_challenges.find(query, {**PROJECTION, "solution": 0}).skip(skip).limit(limit).to_list(limit)
    return {"challenges": challenges, "total_count": total_docs, "page": page, "pages": (total_docs + limit - 1) // limit}


@router.get("/challenge/{challenge_id}")
async def get_challenge(challenge_id: str, show_solution: bool = False):
    """Get a specific challenge. Solution hidden by default."""
    proj = {**PROJECTION}
    if not show_solution:
        proj["solution"] = 0
    ch = await _db.algo_challenges.find_one({"id": challenge_id}, proj)
    if not ch:
        raise HTTPException(404, f"Challenge '{challenge_id}' not found")
    return {"challenge": ch}


# ═══════════════════════════════════════════════════════════════
# KNOWLEDGE VAULT (AI Tutor Database)
# ═══════════════════════════════════════════════════════════════

@router.get("/vault")
async def get_vault_entries(
    category: Optional[str] = None,
    limit: int = Query(50, le=500),
):
    """Browse the AI Knowledge Vault — the tutor's internal brain."""
    query = {}
    if category:
        query["category"] = category
    entries = await _db.knowledge_vault.find(query, {**PROJECTION, "content": 0}).to_list(limit)
    return {"entries": entries, "total": len(entries)}


@router.get("/vault/categories")
async def get_vault_categories():
    """Get all knowledge vault categories with counts."""
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    results = await _db.knowledge_vault.aggregate(pipeline).to_list(50)
    categories = [{"category": r["_id"], "count": r["count"]} for r in results]
    return {"categories": categories, "total_entries": sum(c["count"] for c in categories)}


@router.get("/vault/entry/{entry_id}")
async def get_vault_entry(entry_id: str):
    """Get a specific knowledge vault entry with full content."""
    entry = await _db.knowledge_vault.find_one({"id": entry_id}, PROJECTION)
    if not entry:
        raise HTTPException(404, f"Vault entry '{entry_id}' not found")
    return {"entry": entry}


@router.get("/vault/search")
async def search_vault(q: str, limit: int = Query(10, le=50)):
    """Search the knowledge vault by keywords."""
    keywords = [w for w in q.lower().split() if len(w) > 2]
    if not keywords:
        return {"results": [], "total": 0}
    or_conditions = []
    for kw in keywords:
        or_conditions.append({"tags": kw})
        or_conditions.append({"topic": {"$regex": kw, "$options": "i"}})
        or_conditions.append({"category": {"$regex": kw, "$options": "i"}})
    entries = await _db.knowledge_vault.find({"$or": or_conditions}, PROJECTION).limit(limit).to_list(limit)
    return {"query": q, "results": entries, "total": len(entries)}


# ═══════════════════════════════════════════════════════════════
# KNOWLEDGE DATABASES (CS, Physics, Rendering, Architecture, History)
# ═══════════════════════════════════════════════════════════════

@router.get("/knowledge-dbs")
async def get_knowledge_databases(domain: Optional[str] = None):
    """Get all knowledge database entries, optionally filtered by domain."""
    query = {}
    if domain:
        query["_domain"] = domain
    entries = await _db.knowledge_databases.find(query, PROJECTION).to_list(500)
    domains = {}
    for e in entries:
        d = e.get("_domain", "unknown")
        if d not in domains:
            domains[d] = []
        domains[d].append(e)
    return {"domains": domains, "total": len(entries)}


@router.get("/knowledge-db/{domain}")
async def get_knowledge_db_by_domain(domain: str):
    """Get a specific knowledge database (cs, physics, rendering, architecture, computing_history)."""
    entries = await _db.knowledge_databases.find({"_domain": domain}, PROJECTION).to_list(200)
    if not entries:
        raise HTTPException(404, f"Knowledge database '{domain}' not found")
    grouped = {}
    for e in entries:
        t = e.get("_type", "other")
        if t not in grouped:
            grouped[t] = []
        grouped[t].append(e)
    total_hours = sum(e.get("hours", 0) for e in entries)
    return {"domain": domain, "data": grouped, "total_entries": len(entries), "total_hours": total_hours}


@router.get("/knowledge-db/{domain}/field/{field_id}")
async def get_knowledge_field(domain: str, field_id: str):
    """Get a specific field/entry from a knowledge database."""
    entry = await _db.knowledge_databases.find_one({"_domain": domain, "id": field_id}, PROJECTION)
    if not entry:
        raise HTTPException(404, f"Field '{field_id}' not found in '{domain}'")
    return {"entry": entry}


# ═══════════════════════════════════════════════════════════════
# INTERACTIVE QUIZZES (10,000)
# ═══════════════════════════════════════════════════════════════

@router.get("/quizzes")
async def get_quizzes(
    domain: Optional[str] = None,
    topic: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = Query(20, le=200),
    skip: int = Query(0, ge=0),
):
    """Get interactive quizzes with pagination and filtering."""
    query = {}
    if domain:
        query["domain"] = domain
    if topic:
        query["topic"] = topic
    if difficulty:
        query["difficulty"] = difficulty
    total = await _db.interactive_quizzes.count_documents(query)
    quizzes = await _db.interactive_quizzes.find(query, {**PROJECTION, "correct_answer": 0, "explanation": 0}).skip(skip).limit(limit).to_list(limit)
    return {"quizzes": quizzes, "total": total, "page_size": limit, "skip": skip}


@router.get("/quizzes/domains")
async def get_quiz_domains():
    """Get all quiz domains with counts and difficulty distribution."""
    pipeline = [
        {"$group": {
            "_id": {"domain": "$domain", "difficulty": "$difficulty"},
            "count": {"$sum": 1}
        }},
        {"$group": {
            "_id": "$_id.domain",
            "total": {"$sum": "$count"},
            "difficulties": {"$push": {"difficulty": "$_id.difficulty", "count": "$count"}}
        }},
        {"$sort": {"total": -1}},
    ]
    results = await _db.interactive_quizzes.aggregate(pipeline).to_list(50)
    domains = []
    for r in results:
        diff_map = {d["difficulty"]: d["count"] for d in r["difficulties"]}
        domains.append({
            "domain": r["_id"],
            "total_quizzes": r["total"],
            "difficulty_distribution": diff_map,
        })
    grand_total = sum(d["total_quizzes"] for d in domains)
    return {"domains": domains, "grand_total": grand_total}


@router.get("/quiz/{quiz_id}")
async def get_quiz(quiz_id: str, show_answer: bool = False):
    """Get a specific quiz. Answer hidden by default for interactive mode."""
    proj = {**PROJECTION}
    if not show_answer:
        proj["correct_answer"] = 0
        proj["explanation"] = 0
    quiz = await _db.interactive_quizzes.find_one({"id": quiz_id}, proj)
    if not quiz:
        raise HTTPException(404, f"Quiz '{quiz_id}' not found")
    return {"quiz": quiz}


@router.post("/quiz/{quiz_id}/answer")
async def check_quiz_answer(quiz_id: str, answer: str = Query(...)):
    """Check if the provided answer is correct. Returns explanation."""
    quiz = await _db.interactive_quizzes.find_one({"id": quiz_id}, PROJECTION)
    if not quiz:
        raise HTTPException(404, f"Quiz '{quiz_id}' not found")
    correct = quiz.get("correct_answer", "")
    is_correct = answer.strip().lower() == correct.strip().lower()
    # XP auto-award
    xp_amt = 10 if is_correct else 2
    try:
        from routes.xp_helper import award_xp
        await award_xp("default_user", "quiz_correct" if is_correct else "quiz_wrong", quiz.get("domain", "general"), xp_amt)
    except: pass
    return {
        "quiz_id": quiz_id,
        "your_answer": answer,
        "correct_answer": correct,
        "is_correct": is_correct,
        "explanation": quiz.get("explanation", ""),
        "points_earned": quiz.get("points", 0) if is_correct else 0,
        "hints": quiz.get("hints", []) if not is_correct else [],
        "xp_awarded": xp_amt,
    }
    # XP auto-award after return is impossible, so we do it before



@router.get("/quizzes/random")
async def get_random_quizzes(
    domain: Optional[str] = None,
    difficulty: Optional[str] = None,
    count: int = Query(10, le=50),
):
    """Get random quizzes for a quiz session."""
    match = {}
    if domain:
        match["domain"] = domain
    if difficulty:
        match["difficulty"] = difficulty
    pipeline = [{"$match": match}, {"$sample": {"size": count}}, {"$project": {"_id": 0, "correct_answer": 0, "explanation": 0}}]
    quizzes = await _db.interactive_quizzes.aggregate(pipeline).to_list(count)
    return {"quizzes": quizzes, "count": len(quizzes), "session_id": str(hash(str(quizzes)[:100]))}


# ═══════════════════════════════════════════════════════════════
# READING LIBRARY (Books as Classes)
# ═══════════════════════════════════════════════════════════════

@router.get("/reading-library")
async def get_reading_library(category: Optional[str] = None, difficulty: Optional[str] = None):
    """Get all books in the reading library, optionally filtered."""
    query = {}
    if category:
        query["category"] = category
    if difficulty:
        query["difficulty"] = difficulty
    books = await _cdb.reading_library.find(query, {**PROJECTION, "chapters": 0}).to_list(300)
    # Group by category
    categories = {}
    for b in books:
        cat = b.get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(b)
    total_hours = sum(b.get("estimated_hours", 0) for b in books)
    return {"books": books, "categories": categories, "total": len(books), "total_hours": total_hours}


@router.get("/reading-library/categories")
async def get_reading_categories():
    """Get reading library category stats."""
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}, "total_hours": {"$sum": "$estimated_hours"}}},
        {"$sort": {"count": -1}},
    ]
    results = await _cdb.reading_library.aggregate(pipeline).to_list(20)
    from seeds.reading_library import READING_CATEGORIES
    categories = []
    for r in results:
        meta = READING_CATEGORIES.get(r["_id"], {})
        categories.append({
            "id": r["_id"],
            "name": meta.get("name", r["_id"]),
            "icon": meta.get("icon", "book"),
            "color": meta.get("color", "#888"),
            "description": meta.get("description", ""),
            "book_count": r["count"],
            "total_hours": r["total_hours"],
        })
    return {"categories": categories, "total_books": sum(c["book_count"] for c in categories)}


@router.get("/reading-library/book/{book_id}")
async def get_reading_book(book_id: str):
    """Get a specific book with all chapters and lessons."""
    book = await _cdb.reading_library.find_one({"id": book_id}, PROJECTION)
    if not book:
        raise HTTPException(404, f"Book '{book_id}' not found")
    return {"book": book}


@router.get("/reading-library/book/{book_id}/chapter/{chapter_idx}")
async def get_reading_chapter(book_id: str, chapter_idx: int):
    """Get a specific chapter from a book."""
    book = await _cdb.reading_library.find_one({"id": book_id}, PROJECTION)
    if not book:
        raise HTTPException(404, f"Book '{book_id}' not found")
    chapters = book.get("chapters", [])
    if chapter_idx < 0 or chapter_idx >= len(chapters):
        raise HTTPException(404, f"Chapter index {chapter_idx} out of range")
    return {"chapter": chapters[chapter_idx], "book_title": book.get("title", ""), "total_chapters": len(chapters)}


# ═══════════════════════════════════════════════════════════════
# STUDY PATHS
# ═══════════════════════════════════════════════════════════════

@router.get("/study-paths")
async def get_study_paths(category: Optional[str] = None):
    """Get all study paths, optionally filtered by category."""
    query = {}
    if category:
        query["category"] = category
    paths = await _db.study_paths.find(query, {**PROJECTION, "steps": 0}).to_list(50)
    return {"paths": paths, "total": len(paths)}


@router.get("/study-path/{path_id}")
async def get_study_path(path_id: str):
    """Get a specific study path with all steps."""
    path = await _db.study_paths.find_one({"id": path_id}, PROJECTION)
    if not path:
        raise HTTPException(404, f"Study path '{path_id}' not found")
    return {"path": path}


# ═══════════════════════════════════════════════════════════════
# BUG/FIX LIBRARY — Offline Debugging Knowledge
# ═══════════════════════════════════════════════════════════════

@router.get("/bugfix")
async def get_bugfixes(category: Optional[str] = None, severity: Optional[str] = None, limit: int = Query(50, le=200)):
    """Get bug/fix entries, optionally filtered."""
    query = {}
    if category:
        query["category"] = category
    if severity:
        query["severity"] = severity
    entries = await _cdb.bugfix_library.find(query, PROJECTION).limit(limit).to_list(limit)
    return {"entries": entries, "total": len(entries)}


@router.get("/bugfix/search")
async def search_bugfixes(q: str = Query(...), limit: int = Query(20, le=50)):
    """Search the bug/fix library by error message, keywords, or tags."""
    keywords = [w.strip().lower() for w in q.split() if len(w.strip()) > 1]
    if not keywords:
        return {"results": [], "total": 0, "query": q}
    or_conditions = []
    for kw in keywords:
        or_conditions.append({"searchable": {"$regex": kw, "$options": "i"}})
        or_conditions.append({"tags": kw})
    entries = await _cdb.bugfix_library.find({"$or": or_conditions}, PROJECTION).limit(limit).to_list(limit)
    return {"results": entries, "total": len(entries), "query": q}


@router.get("/bugfix/categories")
async def get_bugfix_categories():
    """Get all bugfix categories with counts."""
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    results = await _cdb.bugfix_library.aggregate(pipeline).to_list(30)
    return {"categories": [{"category": r["_id"], "count": r["count"]} for r in results], "total": sum(r["count"] for r in results)}


# ═══════════════════════════════════════════════════════════════
# WORKAROUND LIBRARY
# ═══════════════════════════════════════════════════════════════

@router.get("/workarounds")
async def get_workarounds(category: Optional[str] = None, limit: int = Query(50, le=200)):
    """Get workarounds, optionally filtered by category."""
    q = {"category": category} if category else {}
    entries = await _db.workaround_library.find(q, PROJECTION).limit(limit).to_list(limit)
    return {"workarounds": entries, "total": len(entries)}


@router.get("/workarounds/search")
async def search_workarounds(q: str = Query(...), limit: int = Query(20, le=50)):
    """Search the workaround library."""
    entries = await _db.workaround_library.find(
        {"searchable": {"$regex": q.lower()[:100], "$options": "i"}}, PROJECTION
    ).limit(limit).to_list(limit)
    return {"results": entries, "total": len(entries), "query": q}


@router.get("/workarounds/categories")
async def get_workaround_categories():
    """Get workaround categories with counts."""
    pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    results = await _db.workaround_library.aggregate(pipeline).to_list(30)
    return {"categories": [{"category": r["_id"], "count": r["count"]} for r in results], "total": sum(r["count"] for r in results)}


# ═══════════════════════════════════════════════════════════════
# ACHIEVEMENTS CATALOG (10,000)
# ═══════════════════════════════════════════════════════════════

@router.get("/achievements")
async def get_achievements_catalog(category: Optional[str] = None, rarity: Optional[str] = None, limit: int = Query(100, le=500), skip: int = Query(0, ge=0)):
    """Get achievements catalog with pagination."""
    q = {}
    if category: q["category"] = category
    if rarity: q["rarity"] = rarity
    achs = await _db.achievements_catalog.find(q, PROJECTION).skip(skip).limit(limit).to_list(limit)
    total = await _db.achievements_catalog.count_documents(q)
    return {"achievements": achs, "total": total, "showing": len(achs), "skip": skip}

@router.get("/achievements/stats")
async def get_achievements_stats():
    """Get achievement stats by category and rarity."""
    pipeline = [{"$group": {"_id": {"category": "$category", "rarity": "$rarity"}, "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    results = await _db.achievements_catalog.aggregate(pipeline).to_list(200)
    total = await _db.achievements_catalog.count_documents({})
    by_cat = {}
    by_rarity = {}
    for r in results:
        cat = r["_id"]["category"]
        rar = r["_id"]["rarity"]
        by_cat[cat] = by_cat.get(cat, 0) + r["count"]
        by_rarity[rar] = by_rarity.get(rar, 0) + r["count"]
    return {"total": total, "by_category": by_cat, "by_rarity": by_rarity}


# ═══════════════════════════════════════════════════════════════
# OFFLINE DATA DUMP — Full data for AsyncStorage caching
# ═══════════════════════════════════════════════════════════════

@router.get("/offline/manifest")
async def get_offline_manifest():
    """Get manifest of all cacheable collections with counts and last-modified."""
    collections = {
        "knowledge_databases": await _db.knowledge_databases.count_documents({}),
        "interactive_quizzes": await _db.interactive_quizzes.count_documents({}),
        "reading_library": await _cdb.reading_library.count_documents({}),
        "study_paths": await _db.study_paths.count_documents({}),
        "bugfix_library": await _cdb.bugfix_library.count_documents({}),
        "workaround_library": await _db.workaround_library.count_documents({}),
        "achievements_catalog": await _db.achievements_catalog.count_documents({}),
        "code_snippets": await _db.code_snippets.count_documents({}),
        "cheatsheets": await _db.cheatsheets.count_documents({}),
        "interview_prep": await _db.interview_prep.count_documents({}),
        "flashcard_decks": await _db.flashcard_decks.count_documents({}),
        "http_status_codes": await _db.http_status_codes.count_documents({}),
        "complexity_reference": await _db.complexity_reference.count_documents({}),
        "tech_glossary": await _db.tech_glossary.count_documents({}),
        "career_roadmaps": await _db.career_roadmaps.count_documents({}),
        "project_ideas": await _db.project_ideas.count_documents({}),
    }
    total = sum(collections.values())
    return {"collections": collections, "total_documents": total, "version": "2026-SOTA", "cacheable": True}


@router.get("/offline/dump/{collection}")
async def get_offline_dump(collection: str, skip: int = Query(0, ge=0), limit: int = Query(500, le=2000)):
    """Dump a collection for offline caching. Paginated."""
    allowed = ["knowledge_databases","reading_library","study_paths","bugfix_library","workaround_library","code_snippets","cheatsheets","interview_prep","flashcard_decks","http_status_codes","complexity_reference","tech_glossary","career_roadmaps","project_ideas","achievements_catalog"]
    if collection not in allowed:
        raise HTTPException(400, f"Collection '{collection}' not available for offline dump")
    docs = await _db[collection].find({}, PROJECTION).skip(skip).limit(limit).to_list(limit)
    total = await _db[collection].count_documents({})
    return {"collection": collection, "documents": docs, "count": len(docs), "total": total, "skip": skip, "has_more": skip + limit < total}


# ═══════════════════════════════════════════════════════════════
# PROGRESS TRACKING & QUIZ SCORES
# ═══════════════════════════════════════════════════════════════

@router.post("/progress/update")
async def update_progress(user_id: str = Query("default_user"), item_type: str = Query(...), item_id: str = Query(...), status: str = Query("completed")):
    """Track user progress on any item (book chapter, quiz, track module, etc.)."""
    from datetime import datetime, timezone
    doc = {
        "user_id": user_id,
        "item_type": item_type,
        "item_id": item_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _db.user_progress.update_one(
        {"user_id": user_id, "item_id": item_id},
        {"$set": doc},
        upsert=True
    )
    return {"status": "updated", "item_id": item_id, "progress_status": status}


@router.get("/progress/{user_id}")
async def get_user_progress(user_id: str, item_type: Optional[str] = None):
    """Get all progress for a user."""
    query = {"user_id": user_id}
    if item_type:
        query["item_type"] = item_type
    items = await _db.user_progress.find(query, PROJECTION).to_list(1000)
    completed = sum(1 for i in items if i.get("status") == "completed")
    return {"user_id": user_id, "items": items, "total": len(items), "completed": completed}


@router.post("/quiz-score/save")
async def save_quiz_score(user_id: str = Query("default_user"), domain: str = Query(...), score: int = Query(...), total_questions: int = Query(...), correct: int = Query(...)):
    """Save a quiz session score."""
    from datetime import datetime, timezone
    doc = {
        "user_id": user_id,
        "domain": domain,
        "score": score,
        "total_questions": total_questions,
        "correct": correct,
        "accuracy": round(correct / max(total_questions, 1) * 100, 1),
        "played_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await _db.quiz_scores.insert_one(doc)
    return {"status": "saved", "score": score, "accuracy": doc["accuracy"]}


@router.get("/quiz-scores/{user_id}")
async def get_quiz_scores(user_id: str):
    """Get all quiz scores for a user."""
    scores = await _db.quiz_scores.find({"user_id": user_id}, PROJECTION).sort("played_at", -1).to_list(100)
    total_score = sum(s.get("score", 0) for s in scores)
    total_correct = sum(s.get("correct", 0) for s in scores)
    total_q = sum(s.get("total_questions", 0) for s in scores)
    return {
        "user_id": user_id,
        "scores": scores,
        "total_sessions": len(scores),
        "total_score": total_score,
        "total_correct": total_correct,
        "total_questions": total_q,
        "overall_accuracy": round(total_correct / max(total_q, 1) * 100, 1),
    }


@router.get("/leaderboard")
async def get_leaderboard(limit: int = Query(20, le=100)):
    """Get the quiz leaderboard — top scorers."""
    pipeline = [
        {"$group": {
            "_id": "$user_id",
            "total_score": {"$sum": "$score"},
            "total_correct": {"$sum": "$correct"},
            "total_questions": {"$sum": "$total_questions"},
            "sessions": {"$sum": 1},
        }},
        {"$sort": {"total_score": -1}},
        {"$limit": limit},
        {"$project": {
            "_id": 0,
            "user_id": "$_id",
            "total_score": 1,
            "total_correct": 1,
            "total_questions": 1,
            "sessions": 1,
            "accuracy": {"$round": [{"$multiply": [{"$divide": ["$total_correct", {"$max": ["$total_questions", 1]}]}, 100]}, 1]},
        }},
    ]
    leaders = await _db.quiz_scores.aggregate(pipeline).to_list(limit)
    return {"leaderboard": leaders, "total_players": len(leaders)}



# ═══════════════════════════════════════════════════════════════
# KNOWLEDGE BIBLES
# ═══════════════════════════════════════════════════════════════

@router.get("/bibles")
async def get_all_bibles(
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=500),
    category: str = None
):
    """Get all knowledge bibles (overview, no full articles)."""
    query = {}
    if category:
        # User might pass specific domains like 'security' or 'ml_ai' to the category filter
        regex = {"$regex": category, "$options": "i"}
        query["$or"] = [{"name": regex}, {"description": regex}, {"category": regex}]
    skip = (page - 1) * limit
    total_docs = await _db.bible_entries.count_documents(query)
    bibles = await _db.bible_entries.find(query, {**PROJECTION, "sections": 0}).skip(skip).limit(limit).to_list(limit)
    return {
        "bibles": bibles, 
        "total_count": total_docs,
        "page": page,
        "pages": (total_docs + limit - 1) // limit
    }


@router.get("/bible/{bible_id}")
async def get_bible_detail(bible_id: str):
    """Get a specific bible with all sections and articles."""
    bible = await _db.bible_entries.find_one({"id": bible_id}, PROJECTION)
    if not bible:
        raise HTTPException(404, f"Bible '{bible_id}' not found")
    total_articles = sum(len(s.get("articles", [])) for s in bible.get("sections", []))
    return {"bible": bible, "total_articles": total_articles}


@router.get("/bible/{bible_id}/section/{section_id}")
async def get_bible_section(bible_id: str, section_id: str):
    """Get a specific section from a bible."""
    bible = await _db.bible_entries.find_one({"id": bible_id}, PROJECTION)
    if not bible:
        raise HTTPException(404, f"Bible '{bible_id}' not found")
    section = next((s for s in bible.get("sections", []) if s.get("id") == section_id), None)
    if not section:
        raise HTTPException(404, f"Section '{section_id}' not found")
    return {"section": section, "bible_name": bible.get("name", "")}


@router.get("/bible/{bible_id}/article/{article_id}")
async def get_bible_article(bible_id: str, article_id: str):
    """Get a specific article from a bible."""
    bible = await _db.bible_entries.find_one({"id": bible_id}, PROJECTION)
    if not bible:
        raise HTTPException(404, f"Bible '{bible_id}' not found")
    for section in bible.get("sections", []):
        for article in section.get("articles", []):
            if article.get("id") == article_id:
                return {"article": article, "section_name": section.get("name", ""), "bible_name": bible.get("name", "")}
    raise HTTPException(404, f"Article '{article_id}' not found")


# ═══════════════════════════════════════════════════════════════
# STATS & SEARCH
# ═══════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_academy_stats():
    """Get comprehensive academy statistics."""
    track_count = await _db.academy_tracks.count_documents({})
    subject_count = await _db.academy_subjects.count_documents({})
    bible_count = await _db.bible_entries.count_documents({})
    exercise_count = await _db.exercises.count_documents({})
    project_count = await _db.projects.count_documents({})
    assessment_count = await _db.assessments.count_documents({})
    challenge_count = await _db.algo_challenges.count_documents({})
    vault_count = await _db.knowledge_vault.count_documents({})
    knowledge_db_count = await _db.knowledge_databases.count_documents({})
    quiz_count = await _db.interactive_quizzes.count_documents({})
    game_db_count = await _db.game_database.count_documents({})
    math_db_count = await _db.math_database.count_documents({})
    reading_count = await _cdb.reading_library.count_documents({})
    study_path_count = await _db.study_paths.count_documents({})

    tracks = await _db.academy_tracks.find({}, {"_id": 0, "total_hours": 1, "category": 1}).to_list(200)
    subjects = await _db.academy_subjects.find({}, {"_id": 0, "total_hours": 1}).to_list(100)
    bibles_hrs = await _db.bible_entries.find({}, {"_id": 0, "total_hours": 1}).to_list(100)
    kb_hrs = await _db.knowledge_databases.find({}, {"_id": 0, "hours": 1}).to_list(500)
    total_hours = (
        sum(t.get("total_hours", 0) for t in tracks)
        + sum(s.get("total_hours", 0) for s in subjects)
        + sum(b.get("total_hours", 0) for b in bibles_hrs)
        + sum(k.get("hours", 0) for k in kb_hrs)
    )

    total_content = (track_count + subject_count + bible_count + exercise_count
                     + project_count + assessment_count + challenge_count
                     + vault_count + knowledge_db_count + quiz_count
                     + game_db_count + math_db_count + reading_count)

    return {
        "tracks": track_count,
        "subjects": subject_count,
        "bibles": bible_count,
        "exercises": exercise_count,
        "projects": project_count,
        "assessments": assessment_count,
        "challenges": challenge_count,
        "knowledge_vault_entries": vault_count,
        "knowledge_databases": knowledge_db_count,
        "interactive_quizzes": quiz_count,
        "game_database_entries": game_db_count,
        "math_database_entries": math_db_count,
        "reading_library_books": reading_count,
        "study_paths": study_path_count,
        "total_hours": total_hours,
        "total_content_items": total_content,
    }


@router.get("/search")
async def search_academy(q: str, limit: int = Query(20, le=100)):
    """Search across all academy content using MongoDB regex."""
    results = []
    regex_query = {"$regex": q, "$options": "i"}
    
    # Search tracks
    tracks = await _db.academy_tracks.find(
        {"$or": [{"name": regex_query}, {"description": regex_query}]}, 
        {"id": 1, "name": 1, "description": 1, "_id": 0}
    ).limit(limit).to_list(limit)
    
    for t in tracks:
        results.append({"type": "track", "id": t["id"], "name": t.get("name", ""), "description": t.get("description", "")[:100]})
        
    # Search bibles
    bibles = await _db.bible_entries.find(
        {"$or": [{"name": regex_query}, {"description": regex_query}]}, 
        {"id": 1, "name": 1, "description": 1, "_id": 0}
    ).limit(limit).to_list(limit)
    
    for b in bibles:
        results.append({"type": "bible", "id": b["id"], "name": b.get("name", ""), "description": b.get("description", "")[:100]})
        
    # Search challenges
    challenges = await _db.algo_challenges.find(
        {"$or": [{"title": regex_query}, {"description": regex_query}]}, 
        {"id": 1, "title": 1, "difficulty": 1, "_id": 0}
    ).limit(limit).to_list(limit)
    
    for c in challenges:
        results.append({"type": "challenge", "id": c["id"], "name": c.get("title", ""), "difficulty": c.get("difficulty", "")})

    # Sort results to interleave them, or just limit total
    results = results[:limit]
    return {"query": q, "results": results, "total": len(results)}


# ═══════════════════════════════════════════════════════════════
# ADMIN — Re-seed endpoint
# ═══════════════════════════════════════════════════════════════

@router.post("/admin/reseed")
async def admin_reseed():
    """Force re-seed the database (drops and recreates all academy data)."""
    from seeds.seed_runner import reseed_database
    result = await reseed_database(_db)
    return result


# ═══════════════════════════════════════════════════════════════
# BACKWARD COMPAT — keep old endpoints working
# ═══════════════════════════════════════════════════════════════

@router.get("/topics")
async def get_topics_compat(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    category: str = Query(None),
):
    """Legacy endpoint → redirects to /bibles.

    Passing through as explicit ints (not bare Query objects) so the
    downstream coroutine gets proper integer arithmetic.
    """
    return await get_all_bibles(page=page, limit=limit, category=category)


@router.get("/topic/{topic_id}")
async def get_topic_compat(topic_id: str):
    """Legacy endpoint → redirects to /bible/{id}."""
    return await get_bible_detail(topic_id)


@router.get("/language-tracks")
async def get_language_tracks_compat():
    """Legacy endpoint → redirects to /tracks."""
    return await get_all_tracks(category="language")


@router.get("/daily-challenge")
async def get_daily_challenge():
    """Get a random challenge as today's daily challenge."""
    import random
    from datetime import datetime
    seed = int(datetime.now().strftime('%Y%m%d'))
    challenges = await _db.algo_challenges.find({}, PROJECTION).to_list(200)
    if not challenges:
        return {"id": "dc_empty", "title": "No challenges loaded", "difficulty": "easy"}
    random.seed(seed)
    ch = random.choice(challenges)
    ch.pop("solution", None)
    return ch


@router.get("/interview-problems")
async def get_interview_problems():
    """Get interview problem categories from challenges."""
    challenges = await _db.algo_challenges.find({}, {"_id": 0, "category": 1, "difficulty": 1}).to_list(500)
    categories = {}
    for c in challenges:
        cat = c.get("category", "other")
        if cat not in categories:
            categories[cat] = {"id": cat, "name": cat.replace("-", " ").title(), "count": 0, "difficulty_dist": {}}
        categories[cat]["count"] += 1
        diff = c.get("difficulty", "medium")
        categories[cat]["difficulty_dist"][diff] = categories[cat]["difficulty_dist"].get(diff, 0) + 1
    return {"categories": list(categories.values()), "total_problems": len(challenges)}


@router.get("/certifications")
async def get_certifications():
    """Get available certifications from tracks."""
    tracks = await _db.academy_tracks.find({}, {"_id": 0, "id": 1, "name": 1, "certificate": 1, "color": 1}).to_list(200)
    certs = [{"id": f"cert_{t['id']}", "name": t.get("certificate", f"{t.get('name', '')} Certificate"),
              "track": t["id"], "color": t.get("color", "#8B5CF6")}
             for t in tracks if t.get("certificate")]
    return {"certifications": certs, "total": len(certs)}


@router.get("/cheat-sheets")
async def get_cheat_sheets():
    """Get quick reference cheat sheets."""
    return {
        "cheat_sheets": [
            {"id": "git", "name": "Git Commands", "category": "DevOps", "pages": 2},
            {"id": "sql", "name": "SQL Queries", "category": "Database", "pages": 4},
            {"id": "regex", "name": "Regular Expressions", "category": "Programming", "pages": 2},
            {"id": "docker", "name": "Docker CLI", "category": "DevOps", "pages": 3},
            {"id": "kubernetes", "name": "Kubernetes", "category": "DevOps", "pages": 4},
            {"id": "python", "name": "Python Syntax", "category": "Languages", "pages": 3},
            {"id": "javascript", "name": "JavaScript ES6+", "category": "Languages", "pages": 3},
            {"id": "react", "name": "React Hooks", "category": "Frontend", "pages": 2},
            {"id": "css", "name": "CSS Flexbox/Grid", "category": "Frontend", "pages": 2},
            {"id": "linux", "name": "Linux Commands", "category": "Systems", "pages": 4},
            {"id": "vim", "name": "Vim Cheatsheet", "category": "Tools", "pages": 2},
            {"id": "bash", "name": "Bash Scripting", "category": "Systems", "pages": 3},
            {"id": "http", "name": "HTTP Status Codes", "category": "Web", "pages": 1},
            {"id": "complexity", "name": "Big-O Cheatsheet", "category": "Algorithms", "pages": 2},
        ],
        "total_sheets": 14,
    }
