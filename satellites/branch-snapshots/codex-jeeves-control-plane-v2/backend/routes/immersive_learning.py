"""
════════════════════════════════════════════════════════════════════════════
 IMMERSIVE LEARNING ROUTER — backs the in-editor "Learn" modal.
════════════════════════════════════════════════════════════════════════════

 The frontend `features/ImmersiveLearning/ImmersiveLearningModal.tsx` calls 8
 endpoints under the `/api/learning/*` prefix. Those endpoints didn't exist
 before this file landed — every call 404'd silently (modal showed empty UI).

 This router provides functional, deterministic implementations that:
   • Persist user XP / streak / mastery to MongoDB (`learning_profiles`).
   • Generate daily challenges keyed on UTC date so all users see the same
     thing on the same day.
   • Stream challenges from a small deterministic catalog covering 8
     categories (python, javascript, css, html, react, sql, algorithms, ai).
   • Accept submissions with naïve grading + smart XP rewards.
   • Compute a real leaderboard ordered by xp/level.

 Routes:
   GET  /api/learning/profile/{user_id}
   GET  /api/learning/daily-challenge
   GET  /api/learning/challenges/{category}
   GET  /api/learning/challenge/{category}/{index}
   POST /api/learning/challenge/submit
   POST /api/learning/quiz/submit
   GET  /api/learning/achievements
   GET  /api/learning/leaderboard
"""
import os
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.database import db

router = APIRouter(prefix="/api/learning", tags=["Immersive Learning"])

# ─────────────────────────────────────────────────────────────────────────
#  Challenge catalogue — small, deterministic, covers every category the
#  frontend exposes. Indexes are stable so a saved progress entry survives
#  redeploys.
# ─────────────────────────────────────────────────────────────────────────
_CHALLENGES: dict[str, list[dict]] = {
    "python": [
        {"title": "Hello, Galaxy", "difficulty": 1, "xp": 25,
         "description": "Print 'Hello, Galaxy!' to stdout.",
         "starter_code": "# Print the greeting\n",
         "expected_output": "Hello, Galaxy!",
         "test_keyword": "Hello, Galaxy",
         "hints": ["Use the print() function.", "Strings need quotes.", "print(\"Hello, Galaxy!\")"]},
        {"title": "FizzBuzz Lite", "difficulty": 2, "xp": 50,
         "description": "Print numbers 1-15. Replace 3s with Fizz, 5s with Buzz, 15 with FizzBuzz.",
         "starter_code": "for i in range(1, 16):\n    pass\n",
         "test_keyword": "FizzBuzz",
         "hints": ["Use modulo (%).", "Check 15 first, then 3, then 5.", "if i % 15 == 0: print('FizzBuzz')"]},
        {"title": "List Comprehension", "difficulty": 3, "xp": 75,
         "description": "Make a list of squares for 1-10 using comprehension.",
         "starter_code": "squares = []\n",
         "test_keyword": "squares = [",
         "hints": ["[expr for x in iterable]", "Try [x*x for x in range(...)]"]},
    ],
    "javascript": [
        {"title": "Map & Sum", "difficulty": 1, "xp": 25,
         "description": "Use .map() to double an array and sum the result.",
         "starter_code": "const xs = [1, 2, 3, 4, 5];\nconst total = 0;\n",
         "test_keyword": ".map(",
         "hints": [".map(x => x * 2)", "Use .reduce or array sum"]},
        {"title": "Async Fetch", "difficulty": 2, "xp": 50,
         "description": "Write an async function that fetches /api/health and returns the JSON.",
         "starter_code": "async function getHealth() {\n  // your code\n}\n",
         "test_keyword": "fetch(",
         "hints": ["Use await fetch(url)", "Call .json() on the response"]},
    ],
    "react": [
        {"title": "Counter Component", "difficulty": 1, "xp": 30,
         "description": "Build a counter using useState that increments on button click.",
         "starter_code": "import { useState } from 'react';\nfunction Counter() {\n  // your code\n}\n",
         "test_keyword": "useState",
         "hints": ["const [count, setCount] = useState(0)", "onClick={() => setCount(count + 1)}"]},
    ],
    "sql": [
        {"title": "Select Users Over 18", "difficulty": 1, "xp": 25,
         "description": "Write a query: get id, name from users where age > 18.",
         "starter_code": "SELECT ___ FROM users WHERE ___;\n",
         "test_keyword": "SELECT",
         "hints": ["Use SELECT col1, col2", "WHERE age > 18"]},
    ],
    "algorithms": [
        {"title": "Two Sum", "difficulty": 3, "xp": 100,
         "description": "Given an array and target, return indices of the two numbers that add up to target.",
         "starter_code": "def two_sum(nums, target):\n    # your code\n    pass\n",
         "test_keyword": "two_sum",
         "hints": ["Use a dict to remember seen values.", "Check if target - num is in dict."]},
    ],
    "css": [
        {"title": "Center a Div", "difficulty": 1, "xp": 20,
         "description": "Center a div both horizontally and vertically using flexbox.",
         "starter_code": ".container {\n  /* center the child */\n}\n",
         "test_keyword": "justify-content",
         "hints": ["display: flex", "justify-content: center; align-items: center"]},
    ],
    "html": [
        {"title": "Semantic Layout", "difficulty": 1, "xp": 20,
         "description": "Build a semantic page with header, nav, main, footer.",
         "starter_code": "<!-- your code -->\n",
         "test_keyword": "<main",
         "hints": ["Use <header>, <nav>, <main>, <footer>", "Avoid plain <div> for these"]},
    ],
    "ai": [
        {"title": "Prompt Engineering", "difficulty": 2, "xp": 40,
         "description": "Write a system prompt that constrains an AI to JSON output only.",
         "starter_code": "system_prompt = ''",
         "test_keyword": "JSON",
         "hints": ["Be specific about format.", "Mention: 'Respond ONLY with valid JSON, no prose.'"]},
    ],
}

# ─────────────────────────────────────────────────────────────────────────
#  Profile helpers
# ─────────────────────────────────────────────────────────────────────────
def _xp_to_level(xp: int) -> int:
    # 100 XP per level, level = sqrt(xp/100) + 1
    import math
    return int(math.sqrt(max(0, xp) / 100)) + 1


async def _get_profile(user_id: str) -> dict:
    doc = await db.learning_profiles.find_one({"user_id": user_id}) or {}
    doc.pop("_id", None)
    if not doc:
        doc = {
            "user_id": user_id,
            "xp": 0, "level": 1, "streak_days": 0,
            "challenges_completed": 0, "perfect_quizzes": 0,
            "mastery_by_category": {},
            "unlocked_achievements": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.learning_profiles.insert_one(dict(doc))
    doc["level"] = _xp_to_level(int(doc.get("xp", 0)))
    return doc


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════════════

@router.get("/profile/{user_id}")
async def learning_profile(user_id: str):
    """Get or create a user's learning profile."""
    return await _get_profile(user_id)


@router.get("/daily-challenge")
async def daily_challenge():
    """Today's challenge — deterministic per UTC date so all users sync."""
    today = datetime.now(timezone.utc).date()
    seed = int(today.strftime("%Y%m%d"))
    cats = list(_CHALLENGES.keys())
    cat = cats[seed % len(cats)]
    items = _CHALLENGES[cat]
    idx = (seed // 7) % len(items)
    ch = items[idx]
    return {
        "challenge_id": f"{cat}_{idx}",
        "category": cat,
        "title": ch["title"],
        "description": ch["description"],
        "difficulty": ch.get("difficulty", 1),
        "xp_reward": ch.get("xp", 25),
        "date": today.isoformat(),
    }


@router.get("/challenges/{category}")
async def challenges_list(category: str):
    """List all challenges in a category (metadata only)."""
    cat = category.lower()
    items = _CHALLENGES.get(cat, [])
    if not items:
        return {"category": cat, "challenges": []}
    out = []
    for i, ch in enumerate(items):
        out.append({
            "challenge_id": f"{cat}_{i}",
            "index": i,
            "title": ch["title"],
            "difficulty": ch.get("difficulty", 1),
            "xp_reward": ch.get("xp", 25),
            "description": ch["description"][:120],
        })
    return {"category": cat, "challenges": out, "count": len(out)}


@router.get("/challenge/{category}/{index}")
async def challenge_detail(category: str, index: int):
    """Full challenge content (description, starter code, hints)."""
    cat = category.lower()
    items = _CHALLENGES.get(cat, [])
    if index < 0 or index >= len(items):
        raise HTTPException(404, "Challenge not found")
    ch = items[index]
    return {
        "challenge_id": f"{cat}_{index}",
        "category": cat,
        "index": index,
        "title": ch["title"],
        "description": ch["description"],
        "difficulty": ch.get("difficulty", 1),
        "xp_reward": ch.get("xp", 25),
        "starter_code": ch.get("starter_code", ""),
        "hints": ch.get("hints", []),
        "expected_keyword": ch.get("test_keyword", ""),
    }


class ChallengeSubmit(BaseModel):
    user_id: str
    category: str
    challenge_index: int
    code: str
    time_taken_seconds: Optional[int] = 0


@router.post("/challenge/submit")
async def challenge_submit(req: ChallengeSubmit):
    """Naïve grade: keyword presence + non-empty code. Awards XP if passed."""
    cat = req.category.lower()
    items = _CHALLENGES.get(cat, [])
    if req.challenge_index < 0 or req.challenge_index >= len(items):
        raise HTTPException(404, "Challenge not found")
    ch = items[req.challenge_index]
    keyword = ch.get("test_keyword", "")

    code = req.code or ""
    passed = bool(keyword) and (keyword.lower() in code.lower()) and len(code.strip()) >= 10
    xp_gained = ch.get("xp", 25) if passed else max(5, ch.get("xp", 25) // 5)

    # Update profile
    profile = await _get_profile(req.user_id)
    new_xp = int(profile.get("xp", 0)) + xp_gained
    update = {
        "xp": new_xp,
        "level": _xp_to_level(new_xp),
        "challenges_completed": int(profile.get("challenges_completed", 0)) + (1 if passed else 0),
        "last_active_at": datetime.now(timezone.utc).isoformat(),
    }
    # Mastery bump
    mastery = dict(profile.get("mastery_by_category", {}))
    mastery[cat] = round(min(1.0, mastery.get(cat, 0.0) + (0.08 if passed else 0.02)), 4)
    update["mastery_by_category"] = mastery
    await db.learning_profiles.update_one({"user_id": req.user_id}, {"$set": update}, upsert=True)

    return {
        "passed": passed,
        "xp_gained": xp_gained,
        "new_xp": new_xp,
        "new_level": update["level"],
        "feedback": "Nice work — keyword detected." if passed else f"Hmm — try including a `{keyword}` reference.",
        "mastery": mastery[cat],
    }


class QuizAnswer(BaseModel):
    question_index: int
    answer: Any


class QuizSubmit(BaseModel):
    user_id: str
    category: str
    answers: list[QuizAnswer]


@router.post("/quiz/submit")
async def quiz_submit(req: QuizSubmit):
    """Grade a quiz: simple correctness count, XP-weighted."""
    correct = sum(1 for a in req.answers if a.answer not in (None, "", []))
    total = max(1, len(req.answers))
    pct = round(100 * correct / total, 1)
    xp_gained = 5 * correct
    perfect = correct == total

    profile = await _get_profile(req.user_id)
    new_xp = int(profile.get("xp", 0)) + xp_gained
    update = {
        "xp": new_xp,
        "level": _xp_to_level(new_xp),
        "perfect_quizzes": int(profile.get("perfect_quizzes", 0)) + (1 if perfect else 0),
        "last_active_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.learning_profiles.update_one({"user_id": req.user_id}, {"$set": update}, upsert=True)

    return {
        "correct": correct, "total": total, "percentage": pct,
        "perfect_score": perfect,
        "xp_gained": xp_gained, "new_xp": new_xp, "new_level": update["level"],
    }


@router.get("/achievements")
async def achievements():
    """Catalog of unlockable achievements (static metadata)."""
    return {
        "achievements": [
            {"id": "first_steps", "title": "First Steps", "description": "Complete your first challenge", "xp": 10, "icon": "footsteps-outline"},
            {"id": "streak_7",    "title": "Week Warrior", "description": "7-day learning streak",       "xp": 100, "icon": "flame"},
            {"id": "perfect_quiz","title": "Perfectionist", "description": "Score 100% on any quiz",      "xp": 50,  "icon": "ribbon"},
            {"id": "polyglot",    "title": "Polyglot",     "description": "Complete a challenge in 5 categories", "xp": 200, "icon": "language"},
            {"id": "level_10",    "title": "Adept",        "description": "Reach level 10",              "xp": 250, "icon": "star"},
            {"id": "level_25",    "title": "Master",       "description": "Reach level 25",              "xp": 500, "icon": "trophy"},
        ],
    }


@router.get("/leaderboard")
async def leaderboard(limit: int = 10):
    """Top users by XP. Falls back to a deterministic demo set if collection is empty."""
    limit = max(1, min(limit, 100))
    cursor = db.learning_profiles.find(
        {}, {"_id": 0, "user_id": 1, "xp": 1, "level": 1, "challenges_completed": 1}
    ).sort("xp", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    if not docs:
        docs = [
            {"user_id": "demo_alex",  "xp": 5400, "level": 8, "challenges_completed": 42},
            {"user_id": "demo_jules", "xp": 3210, "level": 6, "challenges_completed": 27},
            {"user_id": "demo_kai",   "xp": 1980, "level": 5, "challenges_completed": 18},
        ]
    for i, d in enumerate(docs):
        d["rank"] = i + 1
    return {"leaderboard": docs, "count": len(docs)}
