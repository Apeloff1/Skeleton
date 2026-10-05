"""
╔══════════════════════════════════════════════════════════════════════════╗
║  30 SOTA ENHANCEMENTS — 2026 Learning Platform Features                ║
║  Code snippets, cheat sheets, interview prep, flashcards,              ║
║  learning analytics, achievements, skill tree, code review,            ║
║  pair programming, project ideas, career roadmap, and more             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Query
from typing import Optional
import os, hashlib, random
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
random.seed(2026)

router = APIRouter(prefix="/api/enhance", tags=["enhancements"])

# Use centralized DB handles so content collections route to content_db
# (reading_library, bugfix_library) while user-facing collections stay on core.
from core.databases import core_db as _db, content_db as _cdb
PROJ = {"_id": 0}


# ══ Enhancement 1: Code Snippet Library ══
@router.get("/snippets")
async def get_code_snippets(language: Optional[str] = None, category: Optional[str] = None, limit: int = Query(20, le=100)):
    q = {}
    if language: q["language"] = language
    if category: q["category"] = category
    snippets = await _db.code_snippets.find(q, PROJ).limit(limit).to_list(limit)
    return {"snippets": snippets, "total": len(snippets)}

# ══ Enhancement 2: Cheat Sheets ══
@router.get("/cheatsheets")
async def get_cheatsheets(topic: Optional[str] = None):
    q = {"topic": topic} if topic else {}
    sheets = await _db.cheatsheets.find(q, PROJ).to_list(100)
    return {"cheatsheets": sheets, "total": len(sheets)}

# ══ Enhancement 3: Interview Prep ══
@router.get("/interview-prep")
async def get_interview_prep(company_type: Optional[str] = None, difficulty: Optional[str] = None):
    q = {}
    if company_type: q["company_type"] = company_type
    if difficulty: q["difficulty"] = difficulty
    questions = await _db.interview_prep.find(q, PROJ).to_list(100)
    return {"questions": questions, "total": len(questions)}

# ══ Enhancement 4: Flashcard Decks ══
@router.get("/flashcards")
async def get_flashcard_decks(domain: Optional[str] = None):
    q = {"domain": domain} if domain else {}
    decks = await _db.flashcard_decks.find(q, PROJ).to_list(50)
    return {"decks": decks, "total": len(decks)}

# ══ Enhancement 5: Learning Analytics ══
@router.get("/analytics/{user_id}")
async def get_learning_analytics(user_id: str):
    quiz_scores = await _db.quiz_scores.find({"user_id": user_id}, PROJ).to_list(1000)
    progress = await _db.user_progress.find({"user_id": user_id}, PROJ).to_list(1000)
    srs = await _db.srs_cards.find({"user_id": user_id}, PROJ).to_list(50000)
    adaptive = await _db.adaptive_stats.find({"user_id": user_id}, PROJ).to_list(50)
    pomo = await _db.pomodoro_lifetime.find_one({"user_id": user_id}, PROJ)
    streak = await _db.learning_streaks.find_one({"user_id": user_id}, PROJ)
    return {
        "user_id": user_id,
        "quiz_sessions": len(quiz_scores),
        "total_quiz_score": sum(s.get("score", 0) for s in quiz_scores),
        "items_completed": sum(1 for p in progress if p.get("status") == "completed"),
        "srs_cards_learned": len(srs),
        "srs_mature": sum(1 for s in srs if s.get("interval_days", 0) >= 21),
        "domains_tracked": len(adaptive),
        "focus_hours": round((pomo or {}).get("total_focus_minutes", 0) / 60, 1),
        "current_streak": (streak or {}).get("current_streak", 0),
        "streak_tier": (streak or {}).get("streak_tier", "starter"),
    }

# ══ Enhancement 6: Achievement System ══
@router.get("/achievements/{user_id}")
async def get_achievements(user_id: str):
    analytics = await get_learning_analytics(user_id)
    achievements = []
    checks = [
        ("first_quiz", "First Quiz", "Complete your first quiz", analytics["quiz_sessions"] >= 1),
        ("quiz_warrior", "Quiz Warrior", "Complete 10 quiz sessions", analytics["quiz_sessions"] >= 10),
        ("quiz_master", "Quiz Master", "Complete 50 quiz sessions", analytics["quiz_sessions"] >= 50),
        ("srs_beginner", "Memory Apprentice", "Learn 10 SRS cards", analytics["srs_cards_learned"] >= 10),
        ("srs_scholar", "Memory Scholar", "Learn 100 SRS cards", analytics["srs_cards_learned"] >= 100),
        ("srs_sage", "Memory Sage", "Have 50 mature SRS cards", analytics["srs_mature"] >= 50),
        ("focus_1h", "Focused Mind", "1 hour of Pomodoro focus", analytics["focus_hours"] >= 1),
        ("focus_10h", "Deep Worker", "10 hours of Pomodoro focus", analytics["focus_hours"] >= 10),
        ("focus_100h", "Marathon Learner", "100 hours of Pomodoro focus", analytics["focus_hours"] >= 100),
        ("streak_3", "Getting Started", "3-day learning streak", analytics["current_streak"] >= 3),
        ("streak_7", "Week Warrior", "7-day learning streak", analytics["current_streak"] >= 7),
        ("streak_30", "Monthly Champion", "30-day learning streak", analytics["current_streak"] >= 30),
        ("streak_100", "Century Club", "100-day learning streak", analytics["current_streak"] >= 100),
        ("multi_domain", "Renaissance Learner", "Track 5+ domains", analytics["domains_tracked"] >= 5),
        ("polyglot", "Polyglot", "Track 10+ domains", analytics["domains_tracked"] >= 10),
    ]
    for aid, name, desc, unlocked in checks:
        achievements.append({"id": aid, "name": name, "description": desc, "unlocked": unlocked})
    return {"achievements": achievements, "unlocked": sum(1 for a in achievements if a["unlocked"]), "total": len(achievements)}

# ══ Enhancement 7: Skill Tree ══
@router.get("/skill-tree/{user_id}")
async def get_skill_tree(user_id: str):
    adaptive = await _db.adaptive_stats.find({"user_id": user_id}, PROJ).to_list(50)
    tree = {}
    for s in adaptive:
        domain = s.get("domain", "")
        level = s.get("current_level", "intermediate")
        accuracy = s.get("correct_answers", 0) / max(s.get("total_answers", 1), 1)
        tree[domain] = {"level": level, "accuracy": round(accuracy * 100, 1), "mastered": level in ["expert", "master"]}
    return {"user_id": user_id, "skill_tree": tree, "mastered_count": sum(1 for v in tree.values() if v["mastered"])}

# ══ Enhancement 8: Project Ideas Generator ══
@router.get("/project-ideas")
async def get_project_ideas(difficulty: Optional[str] = None, domain: Optional[str] = None, limit: int = Query(10, le=50)):
    q = {}
    if difficulty: q["difficulty"] = difficulty
    if domain: q["domain"] = domain
    projects = await _db.project_ideas.find(q, PROJ).limit(limit).to_list(limit)
    return {"projects": projects, "total": len(projects)}

# ══ Enhancement 9: Career Roadmap ══
@router.get("/career-roadmap")
async def get_career_roadmap(role: Optional[str] = None):
    q = {"role": role} if role else {}
    roadmaps = await _db.career_roadmaps.find(q, PROJ).to_list(50)
    return {"roadmaps": roadmaps, "total": len(roadmaps)}

# ══ Enhancement 10: Code Review Checklist ══
@router.get("/code-review-checklist")
async def get_code_review_checklist(language: Optional[str] = None):
    q = {"language": language} if language else {}
    checklists = await _db.code_review_checklists.find(q, PROJ).to_list(50)
    return {"checklists": checklists, "total": len(checklists)}

# ══ Enhancement 11: Design Pattern Catalog ══
@router.get("/patterns")
async def get_design_patterns(category: Optional[str] = None):
    q = {"category": category} if category else {}
    patterns = await _db.design_pattern_catalog.find(q, PROJ).to_list(100)
    return {"patterns": patterns, "total": len(patterns)}

# ══ Enhancement 12: Algorithm Complexity Reference ══
@router.get("/complexity-reference")
async def get_complexity_reference():
    ref = await _db.complexity_reference.find({}, PROJ).to_list(200)
    return {"reference": ref, "total": len(ref)}

# ══ Enhancement 13: System Design Templates ══
@router.get("/system-design-templates")
async def get_system_design_templates():
    templates = await _db.system_design_templates.find({}, PROJ).to_list(50)
    return {"templates": templates, "total": len(templates)}

# ══ Enhancement 14: Keyboard Shortcuts Reference ══
@router.get("/shortcuts")
async def get_keyboard_shortcuts(tool: Optional[str] = None):
    q = {"tool": tool} if tool else {}
    shortcuts = await _db.keyboard_shortcuts.find(q, PROJ).to_list(200)
    return {"shortcuts": shortcuts, "total": len(shortcuts)}

# ══ Enhancement 15: Regex Reference ══
@router.get("/regex-reference")
async def get_regex_reference():
    ref = await _db.regex_reference.find({}, PROJ).to_list(200)
    return {"reference": ref, "total": len(ref)}

# ══ Enhancement 16: HTTP Status Code Reference ══
@router.get("/http-status-codes")
async def get_http_status_codes():
    codes = await _db.http_status_codes.find({}, PROJ).to_list(100)
    return {"codes": codes, "total": len(codes)}

# ══ Enhancement 17: Git Command Reference ══
@router.get("/git-reference")
async def get_git_reference():
    ref = await _db.git_reference.find({}, PROJ).to_list(200)
    return {"reference": ref, "total": len(ref)}

# ══ Enhancement 18: SQL Reference ══
@router.get("/sql-reference")
async def get_sql_reference():
    ref = await _db.sql_reference.find({}, PROJ).to_list(200)
    return {"reference": ref, "total": len(ref)}

# ══ Enhancement 19: Glossary ══
@router.get("/glossary")
async def get_glossary(letter: Optional[str] = None):
    q = {}
    if letter: q["letter"] = letter.upper()
    terms = await _db.tech_glossary.find(q, PROJ).to_list(500)
    return {"terms": terms, "total": len(terms)}

# ══ Enhancement 20: Quick Tips ══
@router.get("/quick-tips")
async def get_quick_tips(category: Optional[str] = None, limit: int = Query(10, le=50)):
    q = {"category": category} if category else {}
    tips = await _db.quick_tips.find(q, PROJ).limit(limit).to_list(limit)
    return {"tips": tips, "total": len(tips)}

# ══ Enhancement 21: Comparison Tables ══
@router.get("/comparisons")
async def get_comparisons(topic: Optional[str] = None):
    q = {"topic": topic} if topic else {}
    comparisons = await _db.comparison_tables.find(q, PROJ).to_list(50)
    return {"comparisons": comparisons, "total": len(comparisons)}

# ══ Enhancement 22: Error Message Decoder ══
@router.get("/decode-error")
async def decode_error(error_message: str = Query(...)):
    results = await _cdb.bugfix_library.find(
        {"searchable": {"$regex": error_message.lower()[:100], "$options": "i"}}, PROJ
    ).limit(10).to_list(10)
    return {"error_message": error_message, "matches": results, "total": len(results)}

# ══ Enhancement 23: Learning Path Progress ══
@router.get("/path-progress/{user_id}/{path_id}")
async def get_path_progress(user_id: str, path_id: str):
    path = await _db.study_paths.find_one({"id": path_id}, PROJ)
    if not path:
        return {"error": "Path not found"}
    progress = await _db.user_progress.find({"user_id": user_id}, PROJ).to_list(1000)
    completed_ids = {p["item_id"] for p in progress if p.get("status") == "completed"}
    steps = path.get("steps", [])
    step_progress = []
    for s in steps:
        ref = s.get("ref", "")
        step_progress.append({**s, "completed": ref in completed_ids})
    completed_count = sum(1 for sp in step_progress if sp["completed"])
    return {"path": path.get("name"), "steps": step_progress, "completed": completed_count, "total": len(steps), "progress_pct": round(completed_count / max(len(steps), 1) * 100, 1)}

# ══ Enhancement 24: Study Session Summary ══
@router.post("/session-summary")
async def save_session_summary(
    user_id: str = Query("default_user"),
    duration_minutes: int = Query(...),
    topics_studied: str = Query(""),
    quizzes_completed: int = Query(0),
    pages_read: int = Query(0),
    notes: Optional[str] = None,
):
    now = datetime.now(timezone.utc)
    session = {
        "user_id": user_id, "duration_minutes": duration_minutes,
        "topics_studied": topics_studied.split(",") if topics_studied else [],
        "quizzes_completed": quizzes_completed, "pages_read": pages_read,
        "notes": notes, "created_at": now.isoformat(),
    }
    await _db.study_sessions.insert_one(session)
    session.pop("_id", None)
    return {"saved": True, "session": session}

# ══ Enhancement 25: Study Sessions History ══
@router.get("/session-history/{user_id}")
async def get_session_history(user_id: str, limit: int = Query(30, le=100)):
    sessions = await _db.study_sessions.find({"user_id": user_id}, PROJ).sort("created_at", -1).limit(limit).to_list(limit)
    total_min = sum(s.get("duration_minutes", 0) for s in sessions)
    return {"sessions": sessions, "total": len(sessions), "total_hours": round(total_min / 60, 1)}

# ══ Enhancement 26: Bookmarks ══
@router.post("/bookmark")
async def save_bookmark(user_id: str = Query("default_user"), item_type: str = Query(...), item_id: str = Query(...), title: str = Query("")):
    now = datetime.now(timezone.utc)
    await _db.bookmarks.update_one(
        {"user_id": user_id, "item_id": item_id},
        {"$set": {"user_id": user_id, "item_type": item_type, "item_id": item_id, "title": title, "created_at": now.isoformat()}},
        upsert=True,
    )
    return {"bookmarked": True, "item_id": item_id}

@router.get("/bookmarks/{user_id}")
async def get_bookmarks(user_id: str):
    bookmarks = await _db.bookmarks.find({"user_id": user_id}, PROJ).to_list(500)
    return {"bookmarks": bookmarks, "total": len(bookmarks)}

@router.delete("/bookmark")
async def remove_bookmark(user_id: str = Query("default_user"), item_id: str = Query(...)):
    await _db.bookmarks.delete_one({"user_id": user_id, "item_id": item_id})
    return {"removed": True, "item_id": item_id}

# ══ Enhancement 27: Notes System ══
@router.post("/note")
async def save_note(user_id: str = Query("default_user"), item_id: str = Query(...), content: str = Query(...)):
    now = datetime.now(timezone.utc)
    await _db.user_notes.update_one(
        {"user_id": user_id, "item_id": item_id},
        {"$set": {"user_id": user_id, "item_id": item_id, "content": content, "updated_at": now.isoformat()}},
        upsert=True,
    )
    return {"saved": True, "item_id": item_id}

@router.get("/notes/{user_id}")
async def get_notes(user_id: str):
    notes = await _db.user_notes.find({"user_id": user_id}, PROJ).to_list(500)
    return {"notes": notes, "total": len(notes)}

# ══ Enhancement 28: Export Learning Data ══
@router.get("/export/{user_id}")
async def export_learning_data(user_id: str):
    analytics = await get_learning_analytics(user_id)
    achievements = await get_achievements(user_id)
    bookmarks = await _db.bookmarks.find({"user_id": user_id}, PROJ).to_list(500)
    notes = await _db.user_notes.find({"user_id": user_id}, PROJ).to_list(500)
    return {"user_id": user_id, "analytics": analytics, "achievements": achievements, "bookmarks": bookmarks, "notes": notes, "exported_at": datetime.now(timezone.utc).isoformat()}

# ══ Enhancement 29: Learning Goals ══
@router.post("/goal")
async def set_learning_goal(user_id: str = Query("default_user"), goal_type: str = Query(...), target: int = Query(...), description: str = Query("")):
    now = datetime.now(timezone.utc)
    await _db.learning_goals.update_one(
        {"user_id": user_id, "goal_type": goal_type},
        {"$set": {"user_id": user_id, "goal_type": goal_type, "target": target, "description": description, "created_at": now.isoformat()}},
        upsert=True,
    )
    return {"set": True, "goal_type": goal_type, "target": target}

@router.get("/goals/{user_id}")
async def get_learning_goals(user_id: str):
    goals = await _db.learning_goals.find({"user_id": user_id}, PROJ).to_list(20)
    return {"goals": goals, "total": len(goals)}

# ══ Enhancement 30: Platform Stats (Public) ══
@router.get("/platform-stats")
async def get_platform_stats():
    tracks = await _db.academy_tracks.count_documents({})
    books = await _cdb.reading_library.count_documents({})
    quizzes = await _db.interactive_quizzes.count_documents({})
    bugfixes = await _cdb.bugfix_library.count_documents({})
    paths = await _db.study_paths.count_documents({})
    kbs = await _db.knowledge_databases.count_documents({})
    vault = await _db.knowledge_vault.count_documents({})
    users = await _db.learning_streaks.count_documents({})
    return {
        "platform": "Tutolage",
        "version": "2026 SOTA",
        "tracks": tracks, "books": books, "quizzes": quizzes,
        "bugfix_entries": bugfixes, "study_paths": paths,
        "knowledge_entries": kbs, "vault_entries": vault,
        "active_learners": users,
        "features": [
            "Adaptive Difficulty (Vygotsky ZPD)","SM-2 Spaced Repetition (Anki-style)",
            "Daily Challenges (Interleaving)","Weekly Streak System (7 tiers)",
            "Pomodoro Timer (SRS-integrated)","AI Reader (8 TTS voices, HD)",
            "Bug/Fix Encyclopedia","10 Learning Science Techniques",
            "Achievement System","Skill Tree","Bookmarks & Notes",
            "Learning Analytics","Study Session Tracking","Export Data",
            "Code Snippets","Cheat Sheets","Interview Prep","Flashcards",
            "Project Ideas","Career Roadmaps","Design Patterns","Error Decoder",
            "Complexity Reference","System Design Templates","Regex Reference",
            "HTTP Status Codes","Git Reference","SQL Reference","Tech Glossary",
        ],
    }
