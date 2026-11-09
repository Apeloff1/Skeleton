"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    CODEDOCK INTERACTIVE EDUCATION v11.0.0                     ║
║                                                                               ║
║  Gamified Learning System with AI-Powered Feedback                            ║
║  - Real-time code challenges                                                  ║
║  - Skill assessments                                                          ║
║  - Achievement system                                                         ║
║  - Personalized learning paths                                                ║
║  - AI code review                                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from pathlib import Path

import os
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
from dotenv import load_dotenv
import uuid
import random
import os

# Load environment
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage

router = APIRouter(prefix="/education", tags=["Interactive Education"])

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# ============================================================================
# DATA MODELS
# ============================================================================

class ChallengeSubmission(BaseModel):
    challenge_id: str
    code: str
    language: str = "python"
    user_id: Optional[str] = None

class SkillAssessmentRequest(BaseModel):
    language: str = "python"
    topics: List[str] = ["basics"]
    difficulty: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    question_count: int = Field(5, ge=1, le=20)

class LearningPathRequest(BaseModel):
    current_level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    goals: List[str] = ["web_development"]
    time_commitment: Literal["light", "moderate", "intensive"] = "moderate"
    preferred_languages: List[str] = ["python"]

class CodeReviewRequest(BaseModel):
    code: str = Field(..., min_length=10)
    language: str = "python"
    focus_areas: Optional[List[str]] = None
    skill_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"

# ============================================================================
# CHALLENGE DATABASE
# ============================================================================

CHALLENGES = {
    "python": {
        "beginner": [
            {
                "id": "py_beg_1",
                "title": "Hello World",
                "description": "Print 'Hello, World!' to the console.",
                "starter_code": "# Write your code here\n",
                "test_cases": [{"expected_output": "Hello, World!"}],
                "hints": ["Use the print() function"],
                "xp": 10,
                "time_limit": 60
            },
            {
                "id": "py_beg_2",
                "title": "Sum Two Numbers",
                "description": "Create a function `add(a, b)` that returns the sum of two numbers.",
                "starter_code": "def add(a, b):\n    # Your code here\n    pass\n",
                "test_cases": [
                    {"input": "add(2, 3)", "expected": 5},
                    {"input": "add(-1, 1)", "expected": 0},
                    {"input": "add(0, 0)", "expected": 0}
                ],
                "hints": ["Use the + operator", "Return the result"],
                "xp": 15,
                "time_limit": 120
            },
            {
                "id": "py_beg_3",
                "title": "Even or Odd",
                "description": "Create a function `is_even(n)` that returns True if n is even, False otherwise.",
                "starter_code": "def is_even(n):\n    # Your code here\n    pass\n",
                "test_cases": [
                    {"input": "is_even(4)", "expected": True},
                    {"input": "is_even(7)", "expected": False},
                    {"input": "is_even(0)", "expected": True}
                ],
                "hints": ["Use the modulo operator %", "n % 2 == 0 for even"],
                "xp": 20,
                "time_limit": 120
            }
        ],
        "intermediate": [
            {
                "id": "py_int_1",
                "title": "Fibonacci Sequence",
                "description": "Create a function `fibonacci(n)` that returns the nth Fibonacci number (0-indexed).",
                "starter_code": "def fibonacci(n):\n    # Your code here\n    pass\n",
                "test_cases": [
                    {"input": "fibonacci(0)", "expected": 0},
                    {"input": "fibonacci(1)", "expected": 1},
                    {"input": "fibonacci(10)", "expected": 55}
                ],
                "hints": ["Consider iterative or recursive approach", "Handle base cases"],
                "xp": 50,
                "time_limit": 300
            },
            {
                "id": "py_int_2",
                "title": "Palindrome Check",
                "description": "Create a function `is_palindrome(s)` that returns True if the string is a palindrome.",
                "starter_code": "def is_palindrome(s):\n    # Your code here\n    pass\n",
                "test_cases": [
                    {"input": "is_palindrome('racecar')", "expected": True},
                    {"input": "is_palindrome('hello')", "expected": False},
                    {"input": "is_palindrome('A man a plan a canal Panama'.lower().replace(' ', ''))", "expected": True}
                ],
                "hints": ["Compare string with its reverse", "s[::-1] reverses a string"],
                "xp": 40,
                "time_limit": 180
            }
        ],
        "advanced": [
            {
                "id": "py_adv_1",
                "title": "LRU Cache",
                "description": "Implement an LRU (Least Recently Used) cache class with get and put methods.",
                "starter_code": """class LRUCache:
    def __init__(self, capacity: int):
        # Your code here
        pass
    
    def get(self, key: int) -> int:
        # Return value or -1 if not found
        pass
    
    def put(self, key: int, value: int) -> None:
        # Add/update key-value pair
        pass
""",
                "test_cases": [
                    {"description": "Basic get/put operations should work"},
                    {"description": "Should evict least recently used when at capacity"}
                ],
                "hints": ["Use OrderedDict or implement with dict + doubly linked list", "Move accessed items to end"],
                "xp": 150,
                "time_limit": 900
            }
        ]
    },
    "javascript": {
        "beginner": [
            {
                "id": "js_beg_1",
                "title": "Array Sum",
                "description": "Create a function `sumArray(arr)` that returns the sum of all numbers in an array.",
                "starter_code": "function sumArray(arr) {\n  // Your code here\n}\n",
                "test_cases": [
                    {"input": "sumArray([1, 2, 3])", "expected": 6},
                    {"input": "sumArray([])", "expected": 0}
                ],
                "hints": ["Use reduce() or a loop"],
                "xp": 20,
                "time_limit": 120
            }
        ]
    }
}

ACHIEVEMENTS = [
    {"id": "first_code", "name": "First Steps", "description": "Complete your first challenge", "xp": 50, "icon": "🎯"},
    {"id": "streak_3", "name": "On Fire", "description": "Complete 3 challenges in a row", "xp": 100, "icon": "🔥"},
    {"id": "streak_7", "name": "Unstoppable", "description": "7-day coding streak", "xp": 250, "icon": "⚡"},
    {"id": "perfect_10", "name": "Perfect 10", "description": "Complete 10 challenges with 100% score", "xp": 500, "icon": "💯"},
    {"id": "speed_demon", "name": "Speed Demon", "description": "Complete a challenge in under 30 seconds", "xp": 150, "icon": "🏎️"},
    {"id": "polyglot", "name": "Polyglot", "description": "Complete challenges in 3 different languages", "xp": 300, "icon": "🌍"},
    {"id": "bug_hunter", "name": "Bug Hunter", "description": "Find and fix 10 bugs", "xp": 400, "icon": "🐛"},
    {"id": "mentor", "name": "Mentor", "description": "Help others with code reviews", "xp": 350, "icon": "🎓"},
    {"id": "night_owl", "name": "Night Owl", "description": "Code after midnight", "xp": 75, "icon": "🦉"},
    {"id": "early_bird", "name": "Early Bird", "description": "Code before 6 AM", "xp": 75, "icon": "🐦"}
]

# ============================================================================
# AI HELPER
# ============================================================================

async def call_education_ai(prompt: str, system_prompt: str) -> str:
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"edu-{uuid.uuid4().hex[:8]}",
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")
        
        response = await chat.send_message(UserMessage(text=prompt))
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")

# ============================================================================
# EDUCATION ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_education_info():
    """Get Interactive Education system info"""
    return {
        "name": "CodeDock Interactive Education",
        "version": "11.0.0",
        "features": [
            "Real-time coding challenges",
            "AI-powered feedback",
            "Skill assessments",
            "Achievement system",
            "Learning paths",
            "Code reviews",
            "Progress tracking",
            "Gamification"
        ],
        "languages_supported": list(CHALLENGES.keys()),
        "difficulty_levels": ["beginner", "intermediate", "advanced"],
        "total_challenges": sum(
            len(challenges) 
            for lang in CHALLENGES.values() 
            for challenges in lang.values()
        ),
        "total_achievements": len(ACHIEVEMENTS),
        "gamification": {
            "xp_system": True,
            "achievements": True,
            "streaks": True,
            "leaderboards": True,
            "badges": True
        }
    }

@router.get("/challenges/{language}")
async def get_challenges(language: str, difficulty: str = "beginner"):
    
    
    diff_map = {
        "beginner": "easy",
        "intermediate": "medium",
        "advanced": "hard",
        "expert": "extreme"
    }
    
    mapped_diff = diff_map.get(difficulty.lower(), difficulty.lower())
    query = {"category": language, "difficulty": mapped_diff}
    
    docs = await _db.algo_challenges.find(query, {"_id": 0}).limit(50).to_list(50)
    
    if len(docs) < 10:
        docs.extend(await _db.algo_challenges.find({"difficulty": mapped_diff}, {"_id": 0}).limit(50 - len(docs)).to_list(50))
        if len(docs) < 10:
            docs.extend(await _db.algo_challenges.find({}, {"_id": 0}).limit(50 - len(docs)).to_list(50))
            
    return {"challenges": docs}
    
    return {
        "language": language,
        "challenges_by_difficulty": {
            diff: len(challs) for diff, challs in lang_challenges.items()
        },
        "all_challenges": lang_challenges
    }

@router.get("/challenge/{challenge_id}")
async def get_challenge(challenge_id: str, language: str = "python"):
    """Get a specific challenge by ID"""
    doc = await _db.algo_challenges.find_one({"id": challenge_id}, {"_id": 0})
    if not doc:
        return {
            "id": challenge_id,
            "title": f"Challenge {challenge_id}",
            "description": "A dynamic hyperscale challenge.",
            "difficulty": "hard",
            "category": language,
            "starter_code": f"// Start coding {language} here",
            "test_cases": [{"input": "test", "expected": "output"}],
            "hints": ["Use your brain"]
        }
    return doc

@router.post("/submit")
async def submit_challenge(submission: ChallengeSubmission):
    """Submit a challenge solution for evaluation"""
    request_id = str(uuid.uuid4())
    
    # Find the challenge
    challenge = None
    for lang, difficulties in CHALLENGES.items():
        for diff, challenges in difficulties.items():
            for c in challenges:
                if c["id"] == submission.challenge_id:
                    challenge = c
                    break
    
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    system_prompt = """You are a coding instructor evaluating student submissions.
Be encouraging but accurate. Provide specific feedback.
Grade fairly but help students learn from mistakes."""

    prompt = f"""Evaluate this code submission:

**Challenge:** {challenge['title']}
**Description:** {challenge['description']}
**Test Cases:** {challenge.get('test_cases', [])}

**Student's Code:**
```{submission.language}
{submission.code}
```

**Evaluate:**
1. **Correctness** (0-100): Does it solve the problem?
2. **Code Quality** (0-100): Is it well-written?
3. **Efficiency** (0-100): Is it efficient?

**Provide:**
- Overall score (0-100)
- Pass/Fail status
- Specific feedback on what's good
- Specific feedback on what could improve
- If wrong, hint towards the solution without giving it away
- XP earned (based on score and challenge XP of {challenge['xp']})

Format as JSON:
{{
    "passed": true/false,
    "score": 0-100,
    "correctness": 0-100,
    "quality": 0-100,
    "efficiency": 0-100,
    "xp_earned": number,
    "feedback": "string",
    "improvements": ["list of improvements"],
    "praise": ["list of good things"]
}}"""

    try:
        result = await call_education_ai(prompt, system_prompt)
        
        # Try to parse JSON from response
        import json
        try:
            # Find JSON in response
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                evaluation = json.loads(result[json_start:json_end])
            else:
                evaluation = {
                    "passed": "pass" in result.lower() or "correct" in result.lower(),
                    "score": 70,
                    "feedback": result
                }
        except Exception:
            evaluation = {
                "passed": "pass" in result.lower() or "correct" in result.lower(),
                "score": 70,
                "feedback": result
            }
        
        return {
            "id": request_id,
            "challenge_id": submission.challenge_id,
            "status": "evaluated",
            "evaluation": evaluation,
            "challenge": {
                "title": challenge["title"],
                "max_xp": challenge["xp"]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/assess")
async def skill_assessment(request: SkillAssessmentRequest):
    """Generate a skill assessment quiz"""
    request_id = str(uuid.uuid4())
    
    prompt = f"""Create a {request.difficulty} skill assessment for {request.language}.

**Topics:** {', '.join(request.topics)}
**Number of Questions:** {request.question_count}

For each question provide:
1. Question text
2. Code snippet (if applicable)
3. 4 multiple choice options (A, B, C, D)
4. Correct answer
5. Explanation

Format as JSON array:
[
    {{
        "id": 1,
        "question": "text",
        "code": "optional code",
        "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
        "correct": "A",
        "explanation": "why A is correct",
        "topic": "topic name",
        "difficulty": "{request.difficulty}"
    }}
]

Make questions practical and test real understanding, not just memorization."""

    try:
        result = await call_education_ai(prompt, "You create accurate, educational coding assessments.")
        
        # Try to parse JSON
        import json
        try:
            json_start = result.find('[')
            json_end = result.rfind(']') + 1
            if json_start != -1 and json_end > json_start:
                questions = json.loads(result[json_start:json_end])
            else:
                questions = [{"raw_response": result}]
        except Exception:
            questions = [{"raw_response": result}]
        
        return {
            "id": request_id,
            "assessment": {
                "language": request.language,
                "topics": request.topics,
                "difficulty": request.difficulty,
                "question_count": len(questions),
                "time_limit_minutes": request.question_count * 2,
                "passing_score": 70
            },
            "questions": questions,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/learning-path")
async def generate_learning_path(request: LearningPathRequest):
    """Generate a personalized learning path"""
    request_id = str(uuid.uuid4())
    
    time_map = {
        "light": "2-3 hours per week",
        "moderate": "5-7 hours per week",
        "intensive": "10+ hours per week"
    }
    
    prompt = f"""Create a personalized learning path:

**Current Level:** {request.current_level}
**Goals:** {', '.join(request.goals)}
**Time Commitment:** {time_map[request.time_commitment]}
**Languages:** {', '.join(request.preferred_languages)}

Create a structured learning path with:

1. **Overview** - Summary of the path
2. **Prerequisites** - What should already be known
3. **Milestones** - Major checkpoints
4. **Weekly Plan** - Specific topics/activities per week
5. **Projects** - Hands-on projects to build
6. **Resources** - Recommended learning materials
7. **Timeline** - Estimated completion time

Format as a detailed curriculum with clear progression."""

    try:
        result = await call_education_ai(prompt, "You are an expert curriculum designer for coding education.")
        
        return {
            "id": request_id,
            "learning_path": result,
            "parameters": {
                "current_level": request.current_level,
                "goals": request.goals,
                "time_commitment": request.time_commitment,
                "languages": request.preferred_languages
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/code-review")
async def ai_code_review(request: CodeReviewRequest):
    """Get AI-powered code review"""
    request_id = str(uuid.uuid4())
    
    focus = request.focus_areas or ["correctness", "style", "efficiency", "best practices"]
    
    prompt = f"""Review this {request.language} code for a {request.skill_level} developer:

```{request.language}
{request.code}
```

**Focus Areas:** {', '.join(focus)}

Provide feedback as if you're a senior developer mentoring:

1. **Overall Assessment** - Quick summary
2. **What's Good** - Positive aspects to reinforce
3. **Improvements** - Specific suggestions with examples
4. **Learning Points** - Concepts to study further
5. **Refactored Version** - Show improved code
6. **Score** - Rate 1-10 with breakdown

Be encouraging but honest. Adjust complexity of feedback for {request.skill_level} level."""

    try:
        result = await call_education_ai(prompt, "You are a supportive senior developer doing code reviews.")
        
        return {
            "id": request_id,
            "review": result,
            "parameters": {
                "language": request.language,
                "skill_level": request.skill_level,
                "focus_areas": focus,
                "code_length": len(request.code)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/achievements")
async def get_achievements():
    """Get all available achievements"""
    return {
        "achievements": ACHIEVEMENTS,
        "total_xp_available": sum(a["xp"] for a in ACHIEVEMENTS),
        "categories": {
            "completion": [a for a in ACHIEVEMENTS if "complete" in a["description"].lower()],
            "streaks": [a for a in ACHIEVEMENTS if "streak" in a["id"]],
            "special": [a for a in ACHIEVEMENTS if a["id"] in ["night_owl", "early_bird", "speed_demon"]]
        }
    }

@router.get("/daily-challenge")
async def get_daily_challenge():
    """Get today's daily challenge"""
    # Deterministic "random" based on date
    import hashlib
    today = datetime.utcnow().strftime("%Y-%m-%d")
    seed = int(hashlib.md5(today.encode()).hexdigest(), 16)
    random.seed(seed)
    
    # Collect all challenges
    all_challenges = []
    for lang, difficulties in CHALLENGES.items():
        for diff, challenges in difficulties.items():
            for c in challenges:
                all_challenges.append({"language": lang, "difficulty": diff, **c})
    
    daily = random.choice(all_challenges)
    daily["bonus_xp"] = daily["xp"] // 2  # 50% bonus for daily
    daily["expires"] = (datetime.utcnow().replace(hour=23, minute=59, second=59)).isoformat()
    
    return {
        "date": today,
        "daily_challenge": daily
    }
