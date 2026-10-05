"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                      CURRICULUM ENGINE v11.0.0                                ║
║                                                                               ║
║  Complete Learning Management System:                                         ║
║  • Course progression tracking                                                ║
║  • Prerequisites management                                                   ║
║  • Quizzes & assessments                                                     ║
║  • Completion certificates                                                   ║
║  • Learning analytics                                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

# Import CS Classes
from cs_classes import get_class, get_all_classes, get_class_summary
from class_week_generator import expand_class_with_full_weeks, generate_full_week_content

router = APIRouter(prefix="/curriculum", tags=["Curriculum Engine"])

# ============================================================================
# MODELS
# ============================================================================

class ProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class CourseProgress(BaseModel):
    course_id: str
    user_id: str
    status: ProgressStatus = ProgressStatus.NOT_STARTED
    current_week: int = 0
    completed_weeks: List[int] = []
    quiz_scores: Dict[int, float] = {}
    assignments_completed: List[str] = []
    started_at: Optional[str] = None
    last_activity: Optional[str] = None
    completion_percentage: float = 0.0

class QuizSubmission(BaseModel):
    course_id: str
    week: int
    answers: List[Dict[str, Any]]

class CertificateRequest(BaseModel):
    course_id: str
    user_id: str

# ============================================================================
# IN-MEMORY STORAGE (Would be MongoDB in production)
# ============================================================================

user_progress: Dict[str, Dict[str, CourseProgress]] = {}
certificates: Dict[str, List[Dict]] = {}

# ============================================================================
# CURRICULUM ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_curriculum_info():
    """Get curriculum engine information"""
    class_summary = get_class_summary()
    return {
        "name": "CodeDock Curriculum Engine",
        "version": "11.0.0",
        "total_classes": class_summary["total_classes"],
        "total_hours": class_summary["total_hours"],
        "features": [
            "Course progression tracking",
            "Prerequisites management",
            "Interactive quizzes",
            "Code exercises with auto-grading",
            "Completion certificates",
            "Learning analytics",
            "Personalized recommendations",
            "Spaced repetition review"
        ],
        "available_classes": class_summary["classes"]
    }

@router.get("/classes")
async def list_all_classes():
    """Get all available CS classes"""
    classes = get_all_classes()
    return {
        "total": len(classes),
        "classes": [
            {
                "id": c["id"],
                "code": c["code"],
                "title": c["title"],
                "subtitle": c["subtitle"],
                "hours": c["hours"],
                "weeks": c["weeks"] if isinstance(c["weeks"], int) else len(c["weeks"]),
                "level": c["level"],
                "prerequisites": c["prerequisites"]
            }
            for c in classes
        ]
    }

# ─────────────────────────────────────────────────────────────────────
# 2026-05-15 — UNIFIED CURRICULUM INDEX
# Aggregates classes + reading tracks + AI-reader endpoints into a single
# index for the new /curriculum hub screen. Cross-references classes to
# reading tracks via subject-keyword matching.
# ─────────────────────────────────────────────────────────────────────
@router.get("/unified-index")
async def get_unified_curriculum_index():
    """Single document combining classes (CS) + reading tracks + AI reader
    info so the unified curriculum UI can render in one round trip. Includes
    soft subject-matching between classes and reading tracks."""
    try:
        classes = get_all_classes()
        # Soft import the reading_curriculum tracks (best-effort; never fail the index)
        reading_tracks: List[Dict[str, Any]] = []
        try:
            # Direct call into the curriculum module via FastAPI's TestClient is heavy.
            # Instead just import the module's underlying handler.
            import importlib
            rc = importlib.import_module("routes.reading_curriculum")
            handler = getattr(rc, "get_all_tracks", None) or getattr(rc, "list_tracks", None) or getattr(rc, "list_reading_tracks", None)
            if handler:
                tracks_resp = await handler()
                if isinstance(tracks_resp, dict):
                    reading_tracks = tracks_resp.get("tracks", []) or []
        except Exception:
            reading_tracks = []

        # Normalize each track to a stable shape used by the unified index
        def _norm_track(t: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "track_id":       t.get("track_id") or t.get("id") or "",
                "title":          t.get("title") or t.get("name") or "Untitled",
                "description":    t.get("description") or "",
                "tags":           t.get("tags") or [],
                "total_chapters": t.get("total_chapters") or t.get("chapters_count") or t.get("total_modules") or 0,
                "category":       t.get("category") or "",
            }
        norm_tracks = [_norm_track(t) for t in reading_tracks]

        # Subject keywords to map class title/subtitle → reading-track tags/description
        def _keywords(s: str) -> set:
            return {w.lower().strip(".,()") for w in (s or "").split() if len(w) > 3}

        # Build per-class reading suggestions (top 3 by overlap)
        class_index = []
        for c in classes:
            ck = _keywords(c.get("title", "") + " " + c.get("subtitle", ""))
            scored = []
            for t in norm_tracks:
                tk = _keywords(
                    str(t.get("title", "")) + " " +
                    str(t.get("description", "")) + " " +
                    " ".join(t.get("tags", []) or [])
                )
                overlap = len(ck & tk)
                if overlap > 0:
                    scored.append((overlap, t))
            scored.sort(key=lambda x: -x[0])
            top_tracks = [t for _, t in scored[:3]]
            # Soft fallback: if nothing matched, surface first 2 tracks generically
            if not top_tracks and norm_tracks:
                top_tracks = norm_tracks[:2]
            class_index.append({
                "id":            c["id"],
                "code":          c["code"],
                "title":         c["title"],
                "subtitle":      c["subtitle"],
                "hours":         c["hours"],
                "weeks":         c["weeks"] if isinstance(c["weeks"], int) else len(c["weeks"]),
                "level":         c["level"],
                "prerequisites": c["prerequisites"],
                "linked_reading": [
                    {
                        "track_id": t.get("track_id"),
                        "title":    t.get("title"),
                        "chapters": t.get("total_chapters"),
                    }
                    for t in top_tracks
                ],
            })

        return {
            "version": "1.0.0",
            "total_classes":        len(class_index),
            "total_reading_tracks": len(norm_tracks),
            "classes":              class_index,
            "reading_tracks":       norm_tracks[:40],
            "reading_routes": {
                "library":            "/api/academy/reading-library",
                "tracks":             "/api/reading/tracks",
                "track_detail":       "/api/reading/track/{track_id}",
                "ai_reader_speak":    "/api/reader/speak",
                "ai_reader_chapter":  "/api/reader/read-chapter",
                "ai_reader_voices":   "/api/reader/voices",
            },
            "education_routes": {
                "achievements":   "/api/education/achievements",
                "challenges":     "/api/education/challenges",
                "daily":          "/api/education/daily-challenge",
                "learning_path":  "/api/education/learning-path",
            },
        }
    except Exception as e:
        return {"error": str(e)[:200], "version": "1.0.0", "classes": [], "reading_tracks": []}




@router.get("/classes/{class_id}")
async def get_class_details(class_id: str):
    """Get detailed information about a specific class (FULL graduation-level content).
    
    If the underlying class data only has `weeks_summary` (topic lists), the
    class-week-generator deterministically expands every week to include prose
    sections, code examples, exercises, learning objectives, and a rubric.
    """
    class_data = get_class(class_id)
    if not class_data:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found")
    return expand_class_with_full_weeks(class_data)

@router.get("/classes/{class_id}/week/{week_num}")
async def get_class_week(class_id: str, week_num: int):
    """Return the FULL week payload for a single week.

    Includes the deeper fields produced by class_week_generator:
      • prose, code_examples, exercises, learning_objectives
      • lab (problem / starter_code / hints / tests / rubric)
      • glossary (structured term/definition list)
      • comprehension_questions (self-check prompts)
      • assessment_rubric, further_reading
    """
    class_data = get_class(class_id)
    if not class_data:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found")

    expanded = expand_class_with_full_weeks(class_data)
    weeks = expanded.get("weeks", []) or []
    target = None
    for w in weeks:
        if isinstance(w, dict) and int(w.get("week", -1)) == int(week_num):
            target = w
            break
    if not target:
        # Fall through: synthesise if requested week is in range.
        if 1 <= week_num <= len(weeks):
            target = weeks[week_num - 1]
        else:
            raise HTTPException(status_code=404, detail=f"Week {week_num} not found for class '{class_id}'")

    # If the week payload is missing the deeper fields, hydrate via the
    # generator directly (e.g. older cached class shape).
    if "lab" not in target or "glossary" not in target:
        title = target.get("title") or f"Week {week_num}"
        topics = list(target.get("topics") or [])
        rich = generate_full_week_content(
            class_id,
            {"week": int(week_num), "title": title, "topics": topics},
            parent_title=class_data.get("title", class_id),
        )
        # Preserve any already-rendered fields; overlay the generator output.
        merged = {**target, **rich}
        target = merged

    # Augment with class context so the frontend can render a header.
    return {
        **target,
        "class_id": class_id,
        "class_title": class_data.get("title", class_id),
        "class_category": class_data.get("category"),
        "class_code": class_data.get("code"),
    }


@router.get("/classes/{class_id}/week/{week_num}/quiz")
async def get_class_week_quiz(class_id: str, week_num: int):
    """Deterministic 5-question MCQ quiz auto-derived from the week's topics.
    
    Builds questions like:
      "Which topic relates most closely to **<topic A>** as covered this week?"
    Correct answer = topic A. Distractors = other topics in this & adjacent weeks.
    Reproducible: same (class_id, week) always yields the same quiz.
    """
    import hashlib, random
    class_data = get_class(class_id)
    if not class_data:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found")

    # IMPORTANT: many classes store `weeks` as an integer count and the real
    # week list under `weeks_summary`. Always hydrate through the generator
    # before scanning so this endpoint works uniformly for every class.
    expanded = expand_class_with_full_weeks(class_data)
    weeks_src = expanded.get("weeks", [])
    if not isinstance(weeks_src, list):
        weeks_src = class_data.get("weeks_summary", []) or []

    # Find the target week and adjacent weeks for distractor pool
    target = None
    pool: list = []
    for w in weeks_src:
        if not isinstance(w, dict): continue
        topics = list(w.get("topics", []) or [])
        if w.get("week") == week_num:
            target = {"week": w.get("week"), "title": w.get("title", ""), "topics": topics}
        pool.extend(topics)

    if not target:
        raise HTTPException(status_code=404, detail=f"Week {week_num} not found")
    pool = [t for t in pool if t]  # dedupe is fine even with repeats
    if len(pool) < 4:
        pool = pool + ["Big-O analysis", "Loop invariants", "Concurrency", "Memory hierarchy"]

    seed = int(hashlib.sha256(f"{class_id}|{week_num}|quiz".encode()).hexdigest()[:16], 16)
    rnd = random.Random(seed)
    target_topics = target["topics"] if target["topics"] else [target["title"]]
    questions = []
    # Build 5 questions
    for i, topic in enumerate((target_topics * 5)[:5]):
        distractors = [p for p in pool if p != topic]
        rnd.shuffle(distractors)
        opts = [topic] + distractors[:3]
        rnd.shuffle(opts)
        correct_idx = opts.index(topic)
        prompt_styles = [
            f"Which of the following is the **primary** focus of this week's coverage of **{topic}**?",
            f"In the context of week {week_num} ({target['title']}), which entry most closely matches **{topic}**?",
            f"Pick the topic that best summarises this week's treatment of **{topic}**.",
            f"Which of these is the textbook answer when asked about **{topic}**?",
            f"This week's material on **{topic}** is most directly described by:",
        ]
        questions.append({
            "id": f"q_{class_id}_{week_num}_{i+1}",
            "prompt": prompt_styles[i % len(prompt_styles)],
            "options": opts,
            "correct_index": correct_idx,
            "explanation": f"The week's syllabus lists **{topic}** as a direct topic. The other options are adjacent material from related weeks or commonly confused concepts.",
        })

    return {
        "class_id": class_id,
        "week": week_num,
        "title": target["title"],
        "questions": questions,
        "passing_score": 4,   # 4 of 5 to pass
    }
    """Get content for a specific week of a class.
    
    Returns the FULL generator-backed week if the underlying dataset only
    contains a summary. No more 404 'broken promise' on per-week lookup.
    """
    class_data = get_class(class_id)
    if not class_data:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found")

    weeks = class_data.get("weeks", [])
    if isinstance(weeks, list):
        for week in weeks:
            if isinstance(week, dict) and week.get("week") == week_num:
                # If the existing week is sparse (no code_examples / no exercises),
                # still synthesise via the generator. Otherwise return as-is.
                if week.get("code_examples") or week.get("exercises"):
                    return week
                # fall through to generator below
                summary = week
                return generate_full_week_content(
                    class_id=class_data.get("id", class_id),
                    week_summary=summary,
                    parent_title=class_data.get("title", ""),
                )

    weeks_summary = class_data.get("weeks_summary", [])
    for week in weeks_summary:
        if week.get("week") == week_num:
            return generate_full_week_content(
                class_id=class_data.get("id", class_id),
                week_summary=week,
                parent_title=class_data.get("title", ""),
            )

    raise HTTPException(status_code=404, detail=f"Week {week_num} not found")

@router.get("/classes/{class_id}/code-examples")
async def get_class_code_examples(class_id: str):
    """Get all code examples from a class"""
    class_data = get_class(class_id)
    if not class_data:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found")
    
    examples = []
    weeks = class_data.get("weeks", [])
    
    if isinstance(weeks, list):
        for week in weeks:
            if isinstance(week, dict) and "code_examples" in week:
                for example in week["code_examples"]:
                    examples.append({
                        "week": week.get("week"),
                        "week_title": week.get("title"),
                        **example
                    })
    
    return {
        "class_id": class_id,
        "total_examples": len(examples),
        "examples": examples
    }

# ============================================================================
# PROGRESS TRACKING
# ============================================================================

@router.post("/progress/start")
async def start_course(course_id: str, user_id: str = "default_user"):
    """Start a course and begin tracking progress"""
    class_data = get_class(course_id)
    if not class_data:
        raise HTTPException(status_code=404, detail=f"Class '{course_id}' not found")
    
    if user_id not in user_progress:
        user_progress[user_id] = {}
    
    if course_id not in user_progress[user_id]:
        user_progress[user_id][course_id] = CourseProgress(
            course_id=course_id,
            user_id=user_id,
            status=ProgressStatus.IN_PROGRESS,
            current_week=1,
            started_at=datetime.utcnow().isoformat(),
            last_activity=datetime.utcnow().isoformat()
        )
    
    return {
        "status": "started",
        "course_id": course_id,
        "progress": user_progress[user_id][course_id].dict()
    }

@router.get("/progress/{course_id}")
async def get_course_progress(course_id: str, user_id: str = "default_user"):
    """Get progress for a specific course"""
    if user_id in user_progress and course_id in user_progress[user_id]:
        return user_progress[user_id][course_id].dict()
    
    return CourseProgress(
        course_id=course_id,
        user_id=user_id
    ).dict()

@router.post("/progress/{course_id}/complete-week")
async def complete_week(course_id: str, week: int, user_id: str = "default_user"):
    """Mark a week as completed"""
    if user_id not in user_progress or course_id not in user_progress[user_id]:
        raise HTTPException(status_code=400, detail="Course not started")
    
    progress = user_progress[user_id][course_id]
    
    if week not in progress.completed_weeks:
        progress.completed_weeks.append(week)
        progress.completed_weeks.sort()
    
    progress.current_week = max(progress.current_week, week + 1)
    progress.last_activity = datetime.utcnow().isoformat()
    
    # Calculate completion percentage
    class_data = get_class(course_id)
    total_weeks = class_data.get("weeks", 15)
    if isinstance(total_weeks, list):
        total_weeks = len(total_weeks)
    
    progress.completion_percentage = (len(progress.completed_weeks) / total_weeks) * 100
    
    # Check if course is complete
    if progress.completion_percentage >= 100:
        progress.status = ProgressStatus.COMPLETED
    
    return {
        "status": "week_completed",
        "week": week,
        "progress": progress.dict()
    }

@router.post("/progress/{course_id}/quiz")
async def submit_quiz(course_id: str, submission: QuizSubmission, user_id: str = "default_user"):
    """Submit a quiz and receive score"""
    if user_id not in user_progress or course_id not in user_progress[user_id]:
        raise HTTPException(status_code=400, detail="Course not started")
    
    progress = user_progress[user_id][course_id]
    
    # Simulate quiz grading (would be more sophisticated in production)
    correct = sum(1 for a in submission.answers if a.get("correct", False))
    total = len(submission.answers)
    score = (correct / total * 100) if total > 0 else 0
    
    progress.quiz_scores[submission.week] = score
    progress.last_activity = datetime.utcnow().isoformat()
    
    return {
        "status": "quiz_submitted",
        "week": submission.week,
        "score": score,
        "correct": correct,
        "total": total,
        "passed": score >= 70
    }

@router.get("/progress/all")
async def get_all_progress(user_id: str = "default_user"):
    """Get progress for all courses"""
    if user_id not in user_progress:
        return {"user_id": user_id, "courses": []}
    
    return {
        "user_id": user_id,
        "courses": [p.dict() for p in user_progress[user_id].values()]
    }

# ============================================================================
# CERTIFICATES
# ============================================================================

@router.post("/certificate/generate")
async def generate_certificate(request: CertificateRequest):
    """Generate completion certificate"""
    user_id = request.user_id
    course_id = request.course_id
    
    # Verify course completion
    if user_id not in user_progress or course_id not in user_progress[user_id]:
        raise HTTPException(status_code=400, detail="Course not found in progress")
    
    progress = user_progress[user_id][course_id]
    
    if progress.status != ProgressStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Course not yet completed")
    
    # Get class info
    class_data = get_class(course_id)
    
    # Generate certificate
    cert_id = str(uuid.uuid4())
    certificate = {
        "certificate_id": cert_id,
        "user_id": user_id,
        "course_id": course_id,
        "course_title": class_data["title"],
        "course_code": class_data["code"],
        "hours": class_data["hours"],
        "issued_at": datetime.utcnow().isoformat(),
        "average_quiz_score": sum(progress.quiz_scores.values()) / len(progress.quiz_scores) if progress.quiz_scores else 0,
        "verification_url": f"/api/curriculum/certificate/verify/{cert_id}"
    }
    
    # Store certificate
    if user_id not in certificates:
        certificates[user_id] = []
    certificates[user_id].append(certificate)
    
    return certificate

@router.get("/certificate/verify/{cert_id}")
async def verify_certificate(cert_id: str):
    """Verify a certificate"""
    for user_certs in certificates.values():
        for cert in user_certs:
            if cert["certificate_id"] == cert_id:
                return {"valid": True, "certificate": cert}
    
    return {"valid": False, "message": "Certificate not found"}

@router.get("/certificates")
async def get_user_certificates(user_id: str = "default_user"):
    """Get all certificates for a user"""
    if user_id not in certificates:
        return {"user_id": user_id, "certificates": []}
    
    return {
        "user_id": user_id,
        "certificates": certificates[user_id]
    }

# ============================================================================
# LEARNING ANALYTICS
# ============================================================================

@router.get("/analytics")
async def get_learning_analytics(user_id: str = "default_user"):
    """Get learning analytics for a user"""
    if user_id not in user_progress:
        return {
            "user_id": user_id,
            "total_courses_started": 0,
            "total_courses_completed": 0,
            "total_hours_studied": 0,
            "average_quiz_score": 0,
            "learning_streak": 0
        }
    
    courses = user_progress[user_id]
    completed = [p for p in courses.values() if p.status == ProgressStatus.COMPLETED]
    
    all_quiz_scores = []
    for p in courses.values():
        all_quiz_scores.extend(p.quiz_scores.values())
    
    total_hours = sum(
        get_class(p.course_id)["hours"] * (p.completion_percentage / 100)
        for p in courses.values()
        if get_class(p.course_id)
    )
    
    return {
        "user_id": user_id,
        "total_courses_started": len(courses),
        "total_courses_completed": len(completed),
        "total_hours_studied": round(total_hours, 1),
        "average_quiz_score": round(sum(all_quiz_scores) / len(all_quiz_scores), 1) if all_quiz_scores else 0,
        "certificates_earned": len(certificates.get(user_id, [])),
        "skills_acquired": [
            "Data Structures",
            "Algorithms",
            "Object-Oriented Programming",
            "Database Design",
            "SQL",
            "System Design"
        ] if completed else []
    }

# ============================================================================
# RECOMMENDATIONS
# ============================================================================

@router.get("/recommendations")
async def get_recommendations(user_id: str = "default_user"):
    """Get personalized course recommendations"""
    completed_ids = []
    in_progress_ids = []
    
    if user_id in user_progress:
        for course_id, progress in user_progress[user_id].items():
            if progress.status == ProgressStatus.COMPLETED:
                completed_ids.append(course_id)
            elif progress.status == ProgressStatus.IN_PROGRESS:
                in_progress_ids.append(course_id)
    
    all_classes = get_all_classes()
    recommendations = []
    
    for cls in all_classes:
        if cls["id"] not in completed_ids and cls["id"] not in in_progress_ids:
            # Check prerequisites
            prereqs_met = all(
                prereq in completed_ids
                for prereq in cls.get("prerequisites", [])
            )
            
            if prereqs_met or not cls.get("prerequisites"):
                recommendations.append({
                    "course_id": cls["id"],
                    "title": cls["title"],
                    "reason": "Based on your progress" if completed_ids else "Great starting point",
                    "estimated_hours": cls["hours"]
                })
    
    return {
        "user_id": user_id,
        "recommendations": recommendations[:5]
    }
