"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    JEEVES - AI CODE BUTLER v11.0.0                            ║
║                                                                               ║
║  Your Personal AI Coding Tutor & Assistant                                    ║
║  - Personalized teaching style                                                ║
║  - Adaptive difficulty                                                        ║
║  - Context-aware assistance                                                   ║
║  - Code explanation at your level                                             ║
║  - Debugging companion                                                        ║
║  - Best practices mentor                                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import uuid
import os

# Load environment
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage

router = APIRouter(prefix="/jeeves", tags=["Jeeves AI Tutor"])

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# ============================================================================
# DATA MODELS
# ============================================================================

class JeevesRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Your question or request")
    context: Optional[str] = Field(None, description="Code or context")
    skill_level: Literal["beginner", "intermediate", "advanced", "expert"] = "intermediate"
    language: str = "python"
    personality: Literal["formal", "friendly", "encouraging", "concise"] = "friendly"
    session_id: Optional[str] = None

class ExplainRequest(BaseModel):
    code: str = Field(..., min_length=1)
    language: str = "python"
    depth: Literal["eli5", "beginner", "detailed", "expert"] = "beginner"
    focus: Optional[str] = Field(None, description="Specific aspect to focus on")

class DebugHelpRequest(BaseModel):
    code: str = Field(..., min_length=1)
    error: Optional[str] = None
    expected_behavior: Optional[str] = None
    language: str = "python"
    skill_level: str = "intermediate"

class ConceptRequest(BaseModel):
    concept: str = Field(..., min_length=2, description="Programming concept to learn")
    context: Optional[str] = Field(None, description="What you're trying to build")
    skill_level: str = "intermediate"
    include_examples: bool = True
    language: str = "python"

class PracticeRequest(BaseModel):
    topic: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    language: str = "python"
    count: int = Field(3, ge=1, le=10)

# ============================================================================
# JEEVES PERSONALITY SYSTEM
# ============================================================================

JEEVES_PERSONALITIES = {
    "formal": """You are Jeeves, a distinguished AI code butler with impeccable manners.
Speak formally but warmly, like a trusted family butler.
Use phrases like "Very good, sir/madam", "If I may suggest", "Indeed".
Be precise, professional, and thorough in your explanations.""",
    
    "friendly": """You are Jeeves, a friendly and approachable AI coding buddy.
Be warm, encouraging, and conversational.
Use casual language but remain helpful and accurate.
Celebrate successes and be supportive during struggles.""",
    
    "encouraging": """You are Jeeves, an enthusiastic and motivating AI coding coach.
Be extremely positive and encouraging.
Celebrate every small win. Turn mistakes into learning opportunities.
Use phrases like "Great question!", "You've got this!", "Let's figure this out together!".""",
    
    "concise": """You are Jeeves, a no-nonsense AI coding assistant.
Be direct and to the point. Minimize fluff.
Give clear, actionable answers quickly.
Only elaborate when specifically asked."""
}

SKILL_LEVEL_CONTEXT = {
    "beginner": "Explain everything simply. Avoid jargon. Use lots of analogies. Don't assume prior knowledge.",
    "intermediate": "Balance explanation with efficiency. Assume basic programming knowledge. Introduce intermediate concepts.",
    "advanced": "Be technical and precise. Discuss trade-offs, edge cases, and optimizations. Assume strong fundamentals.",
    "expert": "Peer-level discussion. Focus on nuances, advanced patterns, performance implications, and cutting-edge practices."
}

# ============================================================================
# AI HELPER
# ============================================================================

async def call_jeeves(prompt: str, personality: str, skill_level: str, session_id: str = None) -> str:
    try:
        system = f"""{JEEVES_PERSONALITIES.get(personality, JEEVES_PERSONALITIES['friendly'])}

{SKILL_LEVEL_CONTEXT.get(skill_level, SKILL_LEVEL_CONTEXT['intermediate'])}

You help with:
- Explaining code and concepts
- Debugging issues
- Teaching best practices
- Suggesting improvements
- Answering programming questions
- Providing encouragement and motivation

Always be helpful, accurate, and adapt to the user's level."""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id or f"jeeves-{uuid.uuid4().hex[:8]}",
            system_message=system
        ).with_model("openai", "gpt-4o")
        
        response = await chat.send_message(UserMessage(text=prompt))
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Jeeves encountered an issue: {str(e)}")

# ============================================================================
# JEEVES ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_jeeves_info():
    """Meet Jeeves, your AI Code Butler"""
    return {
        "name": "Jeeves",
        "title": "AI Code Butler & Personal Tutor",
        "version": "11.0.0",
        "tagline": "At your service, ready to assist with all your coding needs.",
        "capabilities": [
            "Code explanation at any level",
            "Debugging assistance",
            "Concept teaching",
            "Best practices guidance",
            "Code review",
            "Practice problem generation",
            "Learning path suggestions",
            "Motivation and encouragement"
        ],
        "personalities": {
            "formal": "Distinguished and precise, like a traditional butler",
            "friendly": "Warm and approachable coding buddy",
            "encouraging": "Enthusiastic coach who celebrates your wins",
            "concise": "Direct and efficient, minimal fluff"
        },
        "skill_levels": ["beginner", "intermediate", "advanced", "expert"],
        "languages_fluent": [
            "Python", "JavaScript", "TypeScript", "Java", "C++", "C",
            "Rust", "Go", "Swift", "Kotlin", "Ruby", "PHP", "C#"
        ],
        "specialties": [
            "Data Structures & Algorithms",
            "Object-Oriented Programming",
            "Functional Programming",
            "Web Development",
            "Mobile Development",
            "Database Design",
            "System Design",
            "Testing & QA"
        ]
    }

@router.post("/ask")
async def ask_jeeves(request: JeevesRequest):
    """Ask Jeeves anything about coding"""
    request_id = str(uuid.uuid4())
    
    prompt = f"""User's question: {request.message}

{f'Code/Context:{chr(10)}```{request.language}{chr(10)}{request.context}{chr(10)}```' if request.context else ''}

Language focus: {request.language}

Please help with this query. Remember to adapt your response to a {request.skill_level} level developer."""

    try:
        response = await call_jeeves(prompt, request.personality, request.skill_level, request.session_id)
        
        return {
            "id": request_id,
            "jeeves_response": response,
            "session_id": request.session_id or f"jeeves-{request_id[:8]}",
            "personality": request.personality,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/explain")
async def explain_code(request: ExplainRequest):
    """Have Jeeves explain code in detail"""
    request_id = str(uuid.uuid4())
    
    depth_instructions = {
        "eli5": "Explain like I'm 5 years old. Use simple analogies, no jargon.",
        "beginner": "Explain for someone new to programming. Define terms, be thorough.",
        "detailed": "Comprehensive technical explanation with all details.",
        "expert": "Expert-level analysis: patterns, trade-offs, optimizations, edge cases."
    }
    
    prompt = f"""Please explain this {request.language} code:

```{request.language}
{request.code}
```

{depth_instructions[request.depth]}

{f'Focus specifically on: {request.focus}' if request.focus else ''}

Provide:
1. **Overview** - What does this code do?
2. **Line-by-Line** - Walk through key parts
3. **Key Concepts** - What programming concepts are used?
4. **Potential Issues** - Any bugs or improvements?
5. **Learning Points** - What can be learned from this code?"""

    try:
        response = await call_jeeves(prompt, "friendly", 
                                       "beginner" if request.depth in ["eli5", "beginner"] else "advanced")
        
        return {
            "id": request_id,
            "explanation": response,
            "depth": request.depth,
            "language": request.language,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/debug-help")
async def debug_help(request: DebugHelpRequest):
    """Get Jeeves' help debugging code"""
    request_id = str(uuid.uuid4())
    
    prompt = f"""I need help debugging this {request.language} code:

```{request.language}
{request.code}
```

{f'**Error Message:**{chr(10)}{request.error}' if request.error else ''}
{f'**Expected Behavior:** {request.expected_behavior}' if request.expected_behavior else ''}

Please help me understand:
1. What's wrong with the code?
2. Why is it happening?
3. How do I fix it?
4. How do I prevent this in the future?

Give me the fixed code and explain the changes.
Be supportive - debugging is hard!"""

    try:
        response = await call_jeeves(prompt, "encouraging", request.skill_level)
        
        return {
            "id": request_id,
            "debug_assistance": response,
            "language": request.language,
            "had_error": bool(request.error),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/teach-concept")
async def teach_concept(request: ConceptRequest):
    """Have Jeeves teach you a programming concept"""
    request_id = str(uuid.uuid4())
    
    prompt = f"""Teach me about: **{request.concept}**

Language: {request.language}
My level: {request.skill_level}
{f'I want to use this for: {request.context}' if request.context else ''}

Please provide:
1. **What is it?** - Clear definition
2. **Why use it?** - Benefits and use cases
3. **How does it work?** - Explanation of the mechanics
{'4. **Code Examples** - Practical examples with comments' if request.include_examples else ''}
5. **Common Mistakes** - What to avoid
6. **Best Practices** - How to use it well
7. **Related Concepts** - What to learn next
8. **Practice Exercise** - A small challenge to try

Make it engaging and memorable!"""

    try:
        response = await call_jeeves(prompt, "encouraging", request.skill_level)
        
        return {
            "id": request_id,
            "lesson": response,
            "concept": request.concept,
            "language": request.language,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/practice")
async def generate_practice(request: PracticeRequest):
    """Get practice problems from Jeeves"""
    request_id = str(uuid.uuid4())
    
    prompt = f"""Generate {request.count} {request.difficulty} practice problems about {request.topic} in {request.language}.

For each problem provide:
1. **Problem Title**
2. **Description** - Clear problem statement
3. **Examples** - Input/output examples
4. **Constraints** - Any limitations
5. **Hints** - Progressive hints (don't give away solution)
6. **Starter Code** - Template to begin with
7. **Solution** (hidden) - Correct solution
8. **Explanation** - Why the solution works

Make problems:
- Practical and applicable
- Progressively challenging
- Fun and engaging
- Teaching real skills"""

    try:
        response = await call_jeeves(prompt, "encouraging", 
                                       "intermediate" if request.difficulty == "medium" else 
                                       "beginner" if request.difficulty == "easy" else "advanced")
        
        return {
            "id": request_id,
            "practice_problems": response,
            "topic": request.topic,
            "difficulty": request.difficulty,
            "count": request.count,
            "language": request.language,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/motivate")
async def get_motivation(mood: str = "stuck", context: Optional[str] = None):
    """Get encouragement from Jeeves when you need it"""
    request_id = str(uuid.uuid4())
    
    mood_prompts = {
        "stuck": "The developer is stuck on a problem and feeling frustrated.",
        "imposter": "The developer is experiencing imposter syndrome.",
        "overwhelmed": "The developer is overwhelmed by how much there is to learn.",
        "failed": "The developer's code failed and they're feeling down.",
        "bored": "The developer is bored and losing motivation.",
        "excited": "The developer is excited about a success - celebrate with them!"
    }
    
    prompt = f"""{mood_prompts.get(mood, mood_prompts['stuck'])}

{f'Context: {context}' if context else ''}

Give them a warm, genuine, encouraging message. Include:
1. Acknowledgment of their feelings
2. Perspective (this is normal/temporary)
3. A specific actionable suggestion
4. An inspiring quote or story about famous programmers who faced similar challenges
5. A reminder of how far they've come

Be genuinely supportive, not generic or preachy."""

    try:
        response = await call_jeeves(prompt, "encouraging", "intermediate")
        
        return {
            "id": request_id,
            "message": response,
            "mood": mood,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tip-of-the-day")
async def tip_of_the_day(language: str = "python", level: str = "intermediate"):
    """Get Jeeves' tip of the day"""
    import hashlib
    today = datetime.utcnow().strftime("%Y-%m-%d")
    seed = hashlib.md5(f"{today}-{language}-{level}".encode()).hexdigest()
    
    prompt = f"""Give me one excellent {language} tip for a {level} developer.

The tip should be:
- Practical and immediately useful
- Not too basic, not too obscure
- Include a code example
- Explain why it's useful

Format:
**💡 Tip of the Day**
[The tip]

**Example:**
```{language}
[code example]
```

**Why it matters:**
[explanation]

Seed for variety: {seed}"""

    try:
        response = await call_jeeves(prompt, "friendly", level)
        
        return {
            "date": today,
            "tip": response,
            "language": language,
            "level": level
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# JEEVES ENHANCED - FULL SYSTEM ACCESS v11.2.0
# ============================================================================

# Import MongoDB for vault/log access
from motor.motor_asyncio import AsyncIOMotorClient
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
mongo_client = AsyncIOMotorClient(MONGO_URL)

# Access to all CodeDock databases
vaults_db = mongo_client.codedock_vaults
logs_db = mongo_client.codedock_logs
masterclass_db = mongo_client.codedock_masterclass

class JeevesContextRequest(BaseModel):
    message: str
    skill_level: str = "intermediate"
    personality: str = "friendly"
    session_id: Optional[str] = None
    include_vault: bool = True
    include_logs: bool = True
    include_curriculum: bool = True

@router.post("/ask-with-context")
async def ask_jeeves_with_full_context(request: JeevesContextRequest):
    """Ask Jeeves with full access to vaults, logs, and curriculum"""
    
    context_parts = []
    
    # Gather vault data
    if request.include_vault:
        try:
            code_blocks = await vaults_db.code_blocks.find().limit(20).to_list(20)
            if code_blocks:
                context_parts.append(f"User's saved code ({len(code_blocks)} items): {[c.get('title', 'Untitled') for c in code_blocks]}")
        except Exception:
            pass
    
    # Gather learning history from logs
    if request.include_logs:
        try:
            recent_queries = await logs_db.ai_queries.find().sort("timestamp", -1).limit(10).to_list(10)
            if recent_queries:
                topics = [q.get("query_type", "") for q in recent_queries]
                context_parts.append(f"Recent learning topics: {topics}")
        except Exception:
            pass
    
    # Add curriculum context
    if request.include_curriculum:
        context_parts.append("Available curriculum: 2860+ hours, 12 tracks including Python Mastery, JavaScript Mastery, Game Development, AI/ML, and more.")
    
    # Build enhanced prompt
    context_str = "\\n".join(context_parts) if context_parts else "No additional context available."
    
    prompt = f"""User's question: {request.message}

SYSTEM CONTEXT (Jeeves has access to):
{context_str}

Use this context to provide personalized, relevant assistance. Reference the user's saved code, learning history, or recommend curriculum when relevant.

Respond as a helpful tutor who knows the user's learning journey."""

    try:
        response = await call_jeeves(prompt, request.personality, request.skill_level, request.session_id)
        
        # Log this interaction for training
        try:
            await logs_db.ai_queries.insert_one({
                "query_type": "jeeves_contextual",
                "user_input": request.message[:500],
                "ai_response": response[:1000],
                "model_used": "gpt-4o",
                "timestamp": datetime.utcnow(),
                "context_used": {
                    "vault": request.include_vault,
                    "logs": request.include_logs,
                    "curriculum": request.include_curriculum
                }
            })
        except Exception:
            pass
        
        return {
            "jeeves_response": response,
            "context_used": True,
            "session_id": request.session_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/my-learning-profile")
async def get_learning_profile():
    """Get Jeeves' understanding of the user's learning profile"""
    
    profile = {
        "vault_summary": {},
        "recent_activity": [],
        "strengths": [],
        "areas_for_growth": [],
        "recommended_next": []
    }
    
    # Analyze vault
    try:
        code_count = await vaults_db.code_blocks.count_documents({})
        assets_count = await vaults_db.assets.count_documents({})
        profile["vault_summary"] = {
            "saved_code_blocks": code_count,
            "saved_assets": assets_count
        }
    except Exception:
        pass
    
    # Analyze recent queries
    try:
        queries = await logs_db.ai_queries.find().sort("timestamp", -1).limit(50).to_list(50)
        
        # Count query types
        query_types = {}
        for q in queries:
            qt = q.get("query_type", "unknown")
            query_types[qt] = query_types.get(qt, 0) + 1
        
        # Find most common
        if query_types:
            sorted_types = sorted(query_types.items(), key=lambda x: x[1], reverse=True)
            profile["strengths"] = [t[0] for t in sorted_types[:3] if t[1] > 3]
            profile["areas_for_growth"] = ["Consider exploring: " + topic for topic in ["system_design", "testing", "performance"] if topic not in query_types]
    except Exception:
        pass
    
    # Recommendations based on profile
    profile["recommended_next"] = [
        "Complete the next Masterclass module",
        "Try a Daily Coding Challenge",
        "Review your saved code blocks",
        "Ask Jeeves to explain a new concept"
    ]
    
    return profile

@router.post("/learn-from-interaction")
async def learn_from_interaction(
    interaction_type: str,
    was_helpful: bool,
    feedback: Optional[str] = None
):
    """Allow Jeeves to learn from user interactions"""
    
    try:
        await logs_db.user_actions.insert_one({
            "action_type": "jeeves_feedback",
            "action_data": {
                "interaction_type": interaction_type,
                "was_helpful": was_helpful,
                "feedback": feedback
            },
            "timestamp": datetime.utcnow(),
            "processed": False
        })
        
        return {
            "status": "feedback_recorded",
            "message": "Thank you! I'll use this to improve.",
            "jeeves_says": "Your feedback helps me become a better butler. Most appreciated!" if was_helpful else "I apologize for any confusion. I'll strive to do better."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/curriculum-guide/{track_key}")
async def get_curriculum_guide(track_key: str, skill_level: str = "intermediate"):
    """Get Jeeves' personalized guide for a curriculum track"""
    
    # Import masterclass data
    from routes.masterclass import MASTERCLASS_TRACKS
    
    if track_key not in MASTERCLASS_TRACKS:
        raise HTTPException(status_code=404, detail="Track not found")
    
    track = MASTERCLASS_TRACKS[track_key]
    
    prompt = f"""Create a personalized study guide for the "{track['name']}" track ({track['total_hours']} hours).

Track description: {track['description']}
Student level: {skill_level}

Provide:
1. Recommended study order
2. Time management tips
3. Key concepts to focus on
4. Practice project ideas
5. How this connects to other skills"""

    try:
        response = await call_jeeves(prompt, "encouraging", skill_level)
        
        return {
            "track": track_key,
            "track_name": track["name"],
            "total_hours": track["total_hours"],
            "jeeves_guide": response,
            "interactive_support": True,
            "message": "I'll be here throughout your journey. Don't hesitate to ask questions!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/interactive-lesson")
async def interactive_lesson(
    lesson_topic: str,
    track: Optional[str] = None,
    skill_level: str = "intermediate",
    personality: str = "friendly",
    session_id: Optional[str] = None
):
    """Start an interactive lesson with Jeeves"""
    
    lesson_session = session_id or f"lesson-{uuid.uuid4().hex[:8]}"
    
    prompt = f"""Start an interactive lesson on: {lesson_topic}
{f'Part of track: {track}' if track else ''}

Create an engaging, interactive lesson that:
1. Starts with a hook/real-world example
2. Explains the core concept
3. Provides a simple code example
4. Asks the student a question to check understanding
5. Offers a mini-challenge

Make it conversational and engaging. End with a question for the student to answer."""

    try:
        response = await call_jeeves(prompt, personality, skill_level, lesson_session)
        
        # Log the lesson start
        try:
            await logs_db.user_actions.insert_one({
                "action_type": "lesson_started",
                "action_data": {
                    "topic": lesson_topic,
                    "track": track,
                    "skill_level": skill_level
                },
                "session_id": lesson_session,
                "timestamp": datetime.utcnow()
            })
        except Exception:
            pass
        
        return {
            "lesson_session": lesson_session,
            "topic": lesson_topic,
            "lesson_content": response,
            "interactive": True,
            "next_action": "Reply with your answer to continue the lesson"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# JEEVES DEEP INTEGRATION WITH LOGSCRAPER v11.6 SOTA
# ============================================================================

# Add jeeves_db reference for logscraper integration
jeeves_db = mongo_client.codedock_jeeves

class AdaptiveTutoringRequest(BaseModel):
    user_id: str
    question: str
    context: Optional[str] = None
    preferred_style: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/adaptive-tutoring")
async def adaptive_tutoring(request: AdaptiveTutoringRequest):
    """Jeeves provides deeply personalized tutoring using logscraper insights"""
    
    # Fetch user's comprehensive learning profile from logscraper
    profile = await jeeves_db.learning_profiles.find_one({"user_id": request.user_id})
    patterns = await jeeves_db.patterns.find({"user_id": request.user_id}).to_list(20)
    insights = await jeeves_db.insights.find(
        {"user_id": request.user_id, "acted_upon": False}
    ).sort("priority", -1).to_list(5)
    
    # Build personalized context
    personalization = []
    
    if profile:
        # Struggle areas - be extra patient here
        struggle_areas = profile.get("struggle_areas", [])
        if struggle_areas:
            personalization.append(f"IMPORTANT: User struggles with: {', '.join(struggle_areas[:5])}. Be extra patient and thorough when explaining these topics.")
        
        # Strength areas - can go faster
        strength_areas = profile.get("strength_areas", [])
        if strength_areas:
            personalization.append(f"User is strong in: {', '.join(strength_areas[:5])}. Can reference these as building blocks.")
        
        # Topics studied - avoid redundant explanations
        topics_studied = profile.get("topics_studied", [])
        if topics_studied:
            personalization.append(f"User has studied: {', '.join(topics_studied[:10])}. Assume familiarity with these.")
        
        # Learning velocity - adjust depth
        velocity = profile.get("learning_velocity", 1.0)
        if velocity > 1.5:
            personalization.append("User is a fast learner. Can be more concise and advanced.")
        elif velocity < 0.5:
            personalization.append("User prefers slower pace. Break down concepts into smaller steps.")
        
        # Learning style
        style = profile.get("learning_style_detected")
        if style:
            style_instructions = {
                "visual": "Use diagrams, code examples, and visual analogies.",
                "auditory": "Explain concepts conversationally, use metaphors.",
                "reading/writing": "Provide detailed written explanations and documentation.",
                "kinesthetic": "Focus on hands-on exercises and interactive examples."
            }
            personalization.append(f"Learning style: {style}. {style_instructions.get(style, '')}")
        
        # Engagement score
        engagement = profile.get("engagement_score", 50)
        if engagement < 30:
            personalization.append("User engagement is low. Make responses more engaging and encouraging.")
        elif engagement > 70:
            personalization.append("Highly engaged user. Can include advanced topics and challenges.")
        
        # Game/vault activity
        game_stats = profile.get("game_stats", {})
        if game_stats.get("games_completed", 0) > 5:
            personalization.append("User is an active game creator. Use game development examples when relevant.")
        
        vault_stats = profile.get("vault_stats", {})
        if vault_stats.get("code_saves", 0) > 20:
            personalization.append("User actively saves code. Encourage saving useful snippets.")
    
    # Add patterns-based personalization
    for pattern in patterns:
        pattern_type = pattern.get("pattern_type")
        if pattern_type == "hint_dependent":
            personalization.append("User often needs hints. Proactively offer guidance steps.")
        elif pattern_type == "fast_learner":
            personalization.append("Quick learner. Can provide condensed explanations.")
        elif pattern_type == "night_owl":
            personalization.append("User often learns late. Keep energy high in responses.")
        elif pattern_type == "perseverant_learner":
            personalization.append("User shows great persistence. Acknowledge their effort.")
    
    # Add insights-based adjustments
    for insight in insights[:3]:
        if insight.get("insight_type") == "struggle":
            topic = insight.get("topic")
            if topic:
                personalization.append(f"Recent struggle detected with {topic}. Offer extra support here.")
    
    # Build the personalized prompt
    personalization_str = "\n".join(f"- {p}" for p in personalization) if personalization else "No specific personalization data available."
    
    prompt = f"""USER'S QUESTION: {request.question}

{f'ADDITIONAL CONTEXT: {request.context}' if request.context else ''}

PERSONALIZATION DATA (Use this to tailor your response):
{personalization_str}

Provide a helpful, personalized response that:
1. Directly addresses their question
2. Adapts to their learning style and pace
3. Builds on their existing knowledge
4. Is extra supportive for their struggle areas
5. Provides appropriate level of detail based on their engagement

Be warm, encouraging, and genuinely helpful."""

    try:
        # Determine personality based on user preferences
        personality = request.preferred_style or "encouraging"
        skill_level = profile.get("preferred_difficulty", "intermediate") if profile else "intermediate"
        
        response = await call_jeeves(prompt, personality, skill_level, request.session_id)
        
        # Log this interaction for logscraper
        await logs_db.ai_queries.insert_one({
            "query_type": "adaptive_tutoring",
            "user_id": request.user_id,
            "user_input": request.question[:500],
            "personalization_used": bool(personalization),
            "patterns_count": len(patterns),
            "insights_count": len(insights),
            "timestamp": datetime.utcnow()
        })
        
        return {
            "response": response,
            "personalized": bool(personalization),
            "adaptations_applied": len(personalization),
            "session_id": request.session_id,
            "user_profile_summary": {
                "struggles": profile.get("struggle_areas", [])[:3] if profile else [],
                "strengths": profile.get("strength_areas", [])[:3] if profile else [],
                "learning_style": profile.get("learning_style_detected") if profile else None,
                "engagement_level": "high" if profile and profile.get("engagement_score", 0) > 70 else "medium" if profile and profile.get("engagement_score", 0) > 30 else "building"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user-learning-summary/{user_id}")
async def get_user_learning_summary(user_id: str):
    """Get a comprehensive summary of user's learning journey for Jeeves"""
    
    # Get profile from logscraper
    profile = await jeeves_db.learning_profiles.find_one({"user_id": user_id})
    patterns = await jeeves_db.patterns.find({"user_id": user_id}).to_list(20)
    insights = await jeeves_db.insights.find({"user_id": user_id}).sort("created_at", -1).to_list(10)
    
    # Get recent scrape results
    recent_scrape = await jeeves_db.scrape_results.find_one(
        {"user_id": user_id},
        sort=[("scraped_at", -1)]
    )
    
    # Get game completions
    game_completions = await jeeves_db.game_completions.find(
        {"user_id": user_id}
    ).sort("timestamp", -1).to_list(10)
    
    if not profile:
        return {
            "user_id": user_id,
            "status": "new_user",
            "message": "No learning history found. Start learning to build your profile!",
            "recommendations": [
                "Complete your first challenge",
                "Take a quiz to assess your level",
                "Ask Jeeves a question about coding"
            ],
            "last_scrape": recent_scrape.get("scraped_at").isoformat() if recent_scrape else None
        }
    
    # Compute summary statistics
    challenges = profile.get("challenges_attempted", [])
    passed_challenges = [c for c in challenges if c.get("passed")]
    
    quiz_history = profile.get("quiz_history", [])
    avg_quiz_score = sum(q.get("score", 0) for q in quiz_history) / len(quiz_history) if quiz_history else 0
    
    return {
        "user_id": user_id,
        "status": "active_learner",
        "profile_summary": {
            "topics_mastered": len(profile.get("strength_areas", [])),
            "topics_studying": len(profile.get("topics_studied", [])),
            "topics_struggling": len(profile.get("struggle_areas", [])),
            "total_study_time_hours": round(profile.get("total_study_time_minutes", 0) / 60, 1),
            "session_count": profile.get("session_count", 0),
            "engagement_score": profile.get("engagement_score", 50),
            "learning_velocity": profile.get("learning_velocity", 1.0),
            "learning_style": profile.get("learning_style_detected", "unknown")
        },
        "challenge_stats": {
            "total_attempted": len(challenges),
            "total_passed": len(passed_challenges),
            "success_rate": round(len(passed_challenges) / len(challenges) * 100, 1) if challenges else 0
        },
        "quiz_stats": {
            "quizzes_taken": len(quiz_history),
            "average_score": round(avg_quiz_score, 1)
        },
        "game_stats": profile.get("game_stats", {}),
        "vault_stats": profile.get("vault_stats", {}),
        "ai_interaction_stats": profile.get("ai_interaction_stats", {}),
        "detected_patterns": [
            {
                "type": p.get("pattern_type"),
                "confidence": p.get("confidence"),
                "description": get_pattern_description(p.get("pattern_type"))
            }
            for p in patterns[:5]
        ],
        "recent_insights": [
            {
                "type": i.get("insight_type"),
                "description": i.get("description"),
                "recommendation": i.get("recommendation")
            }
            for i in insights[:3]
        ],
        "recent_games": [
            {
                "game_type": g.get("game_type"),
                "score": g.get("score"),
                "completed_at": g.get("timestamp").isoformat() if g.get("timestamp") else None
            }
            for g in game_completions[:5]
        ],
        "jeeves_recommendations": await generate_jeeves_recommendations(profile, patterns)
    }


def get_pattern_description(pattern_type: str) -> str:
    """Get human-readable description for a pattern type"""
    descriptions = {
        "fast_learner": "Completes challenges quickly and efficiently",
        "hint_dependent": "Often uses hints for guidance",
        "repeated_struggle": "Experiences difficulty with certain topics",
        "game_enthusiast": "Actively creates and plays games",
        "prolific_creator": "Creates many projects and games",
        "vault_power_user": "Organizes code effectively in the vault",
        "ai_collaborator": "Works effectively with AI assistance",
        "night_owl": "Prefers learning late at night",
        "early_bird": "Prefers learning early in the morning",
        "consistent_learner": "Maintains regular study habits",
        "quiz_master": "Achieves high scores on quizzes",
        "perseverant_learner": "Shows persistence in overcoming challenges"
    }
    return descriptions.get(pattern_type, "Learning pattern detected")


async def generate_jeeves_recommendations(profile: Dict, patterns: List) -> List[Dict]:
    """Generate personalized recommendations from Jeeves"""
    recommendations = []
    
    # Based on struggle areas
    struggles = profile.get("struggle_areas", [])
    if struggles:
        recommendations.append({
            "type": "review",
            "title": "Strengthen Foundations",
            "description": f"I noticed you're working through {struggles[0]}. Would you like me to explain it differently?",
            "action": f"Ask Jeeves about {struggles[0]}"
        })
    
    # Based on engagement
    engagement = profile.get("engagement_score", 50)
    if engagement < 40:
        recommendations.append({
            "type": "engagement",
            "title": "Daily Challenge",
            "description": "A quick 5-minute challenge could help build momentum!",
            "action": "Try Daily Challenge"
        })
    
    # Based on patterns
    pattern_types = [p.get("pattern_type") for p in patterns]
    
    if "fast_learner" in pattern_types:
        recommendations.append({
            "type": "advancement",
            "title": "Ready for More",
            "description": "Your quick progress suggests you're ready for expert-level content!",
            "action": "Try Expert Challenges"
        })
    
    if "game_enthusiast" in pattern_types:
        recommendations.append({
            "type": "creation",
            "title": "Share Your Work",
            "description": "You've created some great games! Consider publishing one.",
            "action": "Publish a Game"
        })
    
    if "consistent_learner" in pattern_types:
        recommendations.append({
            "type": "streak",
            "title": "Keep the Streak!",
            "description": "Your consistency is paying off. Don't break the chain!",
            "action": "Continue Learning"
        })
    
    # Default recommendation
    if not recommendations:
        recommendations.append({
            "type": "start",
            "title": "Begin Your Journey",
            "description": "Ready to learn something new? Let's start with a quick lesson!",
            "action": "Start a Lesson"
        })
    
    return recommendations[:3]


@router.post("/log-jeeves-interaction")
async def log_jeeves_interaction(
    user_id: str,
    interaction_type: str,
    topic: Optional[str] = None,
    was_helpful: Optional[bool] = None,
    feedback: Optional[str] = None
):
    """Log a Jeeves interaction for logscraper to process"""
    
    # Determine action type based on interaction
    if was_helpful is True:
        action_type = "jeeves_feedback_positive"
    elif was_helpful is False:
        action_type = "jeeves_feedback_negative"
    else:
        action_type = "jeeves_asked"
    
    # Log to user_actions for logscraper
    await logs_db.user_actions.insert_one({
        "action_id": f"act_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "action_type": action_type,
        "action_data": {
            "interaction_type": interaction_type,
            "topic": topic,
            "was_helpful": was_helpful,
            "feedback": feedback
        },
        "timestamp": datetime.utcnow(),
        "processed": False
    })
    
    return {
        "logged": True,
        "message": "Thank you for your feedback! It helps me improve." if was_helpful is not None else "Interaction logged.",
        "jeeves_says": "I appreciate you letting me know!" if was_helpful else "I'm always here to help!"
    }

# Import the educational curricula
from routes.physics_engine import PHYSICS_CURRICULUM, PHYSICS_SIMULATIONS
from routes.math_engine import MATH_CURRICULUM
from routes.cs_engine import CS_CURRICULUM

# Jeeves' comprehensive knowledge base for game dev education
JEEVES_KNOWLEDGE_BASE = {
    "physics": {
        "total_hours": sum(cat["hours"] for cat in PHYSICS_CURRICULUM.values()),
        "categories": list(PHYSICS_CURRICULUM.keys()),
        "core_topics": [
            "Classical Mechanics for Character Movement",
            "Collision Detection & Response",
            "Rigid Body Dynamics",
            "Soft Body & Cloth Physics",
            "Fluid Simulation",
            "Particle Systems",
            "Quaternions for Rotation"
        ]
    },
    "math": {
        "total_hours": sum(cat["hours"] for cat in MATH_CURRICULUM.values()),
        "categories": list(MATH_CURRICULUM.keys()),
        "core_topics": [
            "Vectors & Vector Operations",
            "Matrix Transformations",
            "Quaternions for 3D Rotation",
            "Bezier Curves & Splines",
            "Perlin & Simplex Noise",
            "Numerical Integration (Euler, RK4)",
            "Probability for Game Balance"
        ]
    },
    "cs": {
        "total_hours": sum(cat["hours"] for cat in CS_CURRICULUM.values()),
        "categories": list(CS_CURRICULUM.keys()),
        "core_topics": [
            "Data Structures (Spatial Trees, Hash Maps)",
            "A* Pathfinding",
            "Behavior Trees & Game AI",
            "ECS Architecture",
            "Rendering Pipeline",
            "Shader Programming",
            "Multiplayer Networking"
        ]
    }
}


class GameDevEducationRequest(BaseModel):
    subject: Literal["physics", "math", "cs", "all"]
    topic: str
    skill_level: str = "intermediate"
    include_code: bool = True
    include_game_examples: bool = True
    language: str = "python"


@router.get("/knowledge-base")
async def get_jeeves_knowledge():
    """Get Jeeves' complete knowledge base for game development education"""
    return {
        "name": "Jeeves Educational Knowledge Base v11.6",
        "description": "Comprehensive Physics, Math, and CS education for Game Development",
        "total_hours": (
            JEEVES_KNOWLEDGE_BASE["physics"]["total_hours"] +
            JEEVES_KNOWLEDGE_BASE["math"]["total_hours"] +
            JEEVES_KNOWLEDGE_BASE["cs"]["total_hours"]
        ),
        "subjects": {
            "physics": {
                "hours": JEEVES_KNOWLEDGE_BASE["physics"]["total_hours"],
                "categories": JEEVES_KNOWLEDGE_BASE["physics"]["categories"],
                "key_topics": JEEVES_KNOWLEDGE_BASE["physics"]["core_topics"]
            },
            "math": {
                "hours": JEEVES_KNOWLEDGE_BASE["math"]["total_hours"],
                "categories": JEEVES_KNOWLEDGE_BASE["math"]["categories"],
                "key_topics": JEEVES_KNOWLEDGE_BASE["math"]["core_topics"]
            },
            "cs": {
                "hours": JEEVES_KNOWLEDGE_BASE["cs"]["total_hours"],
                "categories": JEEVES_KNOWLEDGE_BASE["cs"]["categories"],
                "key_topics": JEEVES_KNOWLEDGE_BASE["cs"]["core_topics"]
            }
        },
        "capabilities": [
            "Interactive physics lessons with simulations",
            "Math tutorials with step-by-step solutions",
            "CS algorithm visualization and explanation",
            "Game-specific application examples",
            "Code implementations in multiple languages",
            "Practice problems with guided solutions"
        ]
    }


@router.post("/teach-physics")
async def teach_physics(
    topic: str,
    skill_level: str = "intermediate",
    include_simulation: bool = True,
    game_context: Optional[str] = None,
    personality: str = "encouraging"
):
    """Have Jeeves teach a physics topic for game development"""
    
    # Find relevant curriculum info
    relevant_modules = []
    for cat_key, category in PHYSICS_CURRICULUM.items():
        for module in category["modules"]:
            if topic.lower() in module["name"].lower() or any(topic.lower() in t.lower() for t in module.get("topics", [])):
                relevant_modules.append({
                    "category": category["name"],
                    "module": module["name"],
                    "topics": module.get("topics", []),
                    "game_applications": module.get("game_applications", [])
                })
    
    curriculum_context = f"Relevant curriculum modules: {relevant_modules}" if relevant_modules else ""
    
    prompt = f"""Teach the physics concept: **{topic}**

{curriculum_context}

Student level: {skill_level}
{f'Game context: {game_context}' if game_context else 'Focus on game development applications'}

Provide a comprehensive lesson including:

1. **Introduction** - What is this concept and why does it matter for games?

2. **The Physics** - Explain the underlying physics clearly
   - Key equations with explanation
   - Intuitive understanding (not just formulas)

3. **Game Development Application** - How is this used in games?
   - Real game examples (mention actual games if possible)
   - Common implementations

4. **Code Implementation** - Show how to implement this
   - Provide working code in Python
   - Comment every important line
   - Show both simple and optimized versions

5. **Common Pitfalls** - What mistakes do developers make?

6. **Practice Problem** - Give a challenge to solidify understanding

{'7. **Interactive Simulation** - Describe a simple simulation they can try' if include_simulation else ''}

Make the lesson engaging and practical. Use analogies where helpful."""

    try:
        response = await call_jeeves(prompt, personality, skill_level)
        
        return {
            "subject": "physics",
            "topic": topic,
            "skill_level": skill_level,
            "lesson": response,
            "relevant_curriculum": relevant_modules,
            "simulations_available": list(PHYSICS_SIMULATIONS.keys()),
            "next_topics": [m["module"] for m in relevant_modules[:3]] if relevant_modules else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/teach-math")
async def teach_math(
    topic: str,
    skill_level: str = "intermediate",
    include_visualization: bool = True,
    game_context: Optional[str] = None,
    language: str = "python",
    personality: str = "encouraging"
):
    """Have Jeeves teach a math topic for game development"""
    
    # Find relevant curriculum info
    relevant_modules = []
    for cat_key, category in MATH_CURRICULUM.items():
        for module in category["modules"]:
            if topic.lower() in module["name"].lower() or any(topic.lower() in t.lower() for t in module.get("topics", [])):
                relevant_modules.append({
                    "category": category["name"],
                    "module": module["name"],
                    "topics": module.get("topics", []),
                    "game_applications": module.get("game_applications", [])
                })
    
    curriculum_context = f"Relevant curriculum modules: {relevant_modules}" if relevant_modules else ""
    
    prompt = f"""Teach the mathematics concept: **{topic}**

{curriculum_context}

Student level: {skill_level}
Programming language: {language}
{f'Game context: {game_context}' if game_context else 'Focus on game development applications'}

Provide a comprehensive lesson including:

1. **Introduction** - What is this concept and why do game developers need it?

2. **The Math** - Explain the mathematics clearly
   - Definitions and notation
   - Key formulas with derivation/explanation
   - Intuitive geometric/visual understanding

3. **Step-by-Step Examples** - Work through 2-3 examples
   - Show every step
   - Explain why each step is taken

4. **Game Development Application** - How is this used in games?
   - Specific use cases (camera systems, physics, animation, etc.)
   - Real game examples

5. **Code Implementation** - Show how to implement this
   - Provide working {language} code
   - Optimized version for game loops
   - Common library functions (numpy, etc.)

6. **Common Mistakes** - What errors do people make with this concept?

7. **Practice Problems** - 3 problems of increasing difficulty with hints

{'8. **Visualization** - Describe how to visualize this concept' if include_visualization else ''}

Make math accessible and show its practical value in game development."""

    try:
        response = await call_jeeves(prompt, personality, skill_level)
        
        return {
            "subject": "math",
            "topic": topic,
            "skill_level": skill_level,
            "language": language,
            "lesson": response,
            "relevant_curriculum": relevant_modules,
            "related_topics": [m["module"] for m in relevant_modules[:3]] if relevant_modules else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/teach-cs")
async def teach_cs(
    topic: str,
    skill_level: str = "intermediate",
    include_complexity: bool = True,
    game_context: Optional[str] = None,
    language: str = "python",
    personality: str = "encouraging"
):
    """Have Jeeves teach a computer science topic for game development"""
    
    # Find relevant curriculum info
    relevant_modules = []
    for cat_key, category in CS_CURRICULUM.items():
        for module in category["modules"]:
            if topic.lower() in module["name"].lower() or any(topic.lower() in t.lower() for t in module.get("topics", [])):
                relevant_modules.append({
                    "category": category["name"],
                    "module": module["name"],
                    "topics": module.get("topics", []),
                    "implementations": module.get("implementations", []),
                    "game_applications": module.get("game_applications", [])
                })
    
    curriculum_context = f"Relevant curriculum modules: {relevant_modules}" if relevant_modules else ""
    
    prompt = f"""Teach the computer science concept: **{topic}**

{curriculum_context}

Student level: {skill_level}
Programming language: {language}
{f'Game context: {game_context}' if game_context else 'Focus on game development applications'}

Provide a comprehensive lesson including:

1. **Introduction** - What is this concept and why is it crucial for games?

2. **The Concept** - Explain the CS fundamentals
   - Core idea and intuition
   - How it works internally
   - Diagrams/visual representation (describe in text)

{'3. **Complexity Analysis** - Big O notation' if include_complexity else '3. **Key Points**'}
   {'- Time complexity' if include_complexity else '- Main advantages'}
   {'- Space complexity' if include_complexity else '- When to use'}
   {'- When this matters in games (frame budget, etc.)' if include_complexity else '- Trade-offs'}

4. **Game Development Application** - How is this used in games?
   - Specific systems that use this (rendering, AI, physics, etc.)
   - Real engine implementations (Unity, Unreal, Godot)

5. **Code Implementation** - Complete working implementation
   - {language} code with detailed comments
   - Both naive and optimized versions
   - Production-ready patterns

6. **Common Pitfalls** - What do developers get wrong?
   - Performance traps
   - Incorrect usage
   - Debugging tips

7. **Practice Challenge** - Implement a game-related feature using this concept

Make CS practical and directly applicable to game development."""

    try:
        response = await call_jeeves(prompt, personality, skill_level)
        
        return {
            "subject": "computer_science",
            "topic": topic,
            "skill_level": skill_level,
            "language": language,
            "lesson": response,
            "relevant_curriculum": relevant_modules,
            "implementations_available": [impl for m in relevant_modules for impl in m.get("implementations", [])]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/game-dev-qa")
async def game_dev_question(
    question: str,
    category: Optional[Literal["physics", "math", "cs", "general"]] = None,
    skill_level: str = "intermediate",
    include_code: bool = True,
    personality: str = "friendly"
):
    """Ask Jeeves any game development question - he knows Physics, Math, and CS!"""
    
    # Build comprehensive context
    knowledge_context = f"""You have comprehensive knowledge of:

**PHYSICS ({JEEVES_KNOWLEDGE_BASE['physics']['total_hours']} hours of curriculum):**
Categories: {', '.join(JEEVES_KNOWLEDGE_BASE['physics']['categories'])}
Core Topics: {', '.join(JEEVES_KNOWLEDGE_BASE['physics']['core_topics'])}

**MATHEMATICS ({JEEVES_KNOWLEDGE_BASE['math']['total_hours']} hours of curriculum):**
Categories: {', '.join(JEEVES_KNOWLEDGE_BASE['math']['categories'])}
Core Topics: {', '.join(JEEVES_KNOWLEDGE_BASE['math']['core_topics'])}

**COMPUTER SCIENCE ({JEEVES_KNOWLEDGE_BASE['cs']['total_hours']} hours of curriculum):**
Categories: {', '.join(JEEVES_KNOWLEDGE_BASE['cs']['categories'])}
Core Topics: {', '.join(JEEVES_KNOWLEDGE_BASE['cs']['core_topics'])}"""
    
    prompt = f"""{knowledge_context}

Student's Question: {question}
{f'Category focus: {category}' if category else 'Answer drawing from all your knowledge'}
Student level: {skill_level}

Provide a helpful, comprehensive answer that:
1. Directly addresses the question
2. Explains underlying concepts
3. Shows practical game dev application
{'4. Includes code examples' if include_code else ''}
5. Suggests related topics to explore

Be the knowledgeable, supportive tutor you are!"""

    try:
        response = await call_jeeves(prompt, personality, skill_level)
        
        return {
            "question": question,
            "category": category or "general",
            "answer": response,
            "knowledge_sources": ["physics", "math", "cs"],
            "jeeves_says": "I'm here to help you master game development. Ask me anything!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/study-path/{goal}")
async def get_study_path(
    goal: str,
    current_level: str = "beginner",
    hours_per_week: int = 10
):
    """Get a personalized study path from Jeeves for a game dev goal"""
    
    prompt = f"""Create a personalized study path for someone who wants to: **{goal}**

Current skill level: {current_level}
Available time: {hours_per_week} hours per week

Available curriculum:
- Physics: {JEEVES_KNOWLEDGE_BASE['physics']['total_hours']} hours ({', '.join(JEEVES_KNOWLEDGE_BASE['physics']['categories'])})
- Math: {JEEVES_KNOWLEDGE_BASE['math']['total_hours']} hours ({', '.join(JEEVES_KNOWLEDGE_BASE['math']['categories'])})
- CS: {JEEVES_KNOWLEDGE_BASE['cs']['total_hours']} hours ({', '.join(JEEVES_KNOWLEDGE_BASE['cs']['categories'])})

Create a structured learning path with:

1. **Phase 1: Foundations** (what to learn first)
   - Essential topics from each subject
   - Estimated time
   - Why these are prerequisites

2. **Phase 2: Core Skills** (main learning phase)
   - Key topics in order
   - Projects to build
   - Milestones

3. **Phase 3: Advanced/Specialization**
   - Deep dive areas
   - Real project work
   - Portfolio pieces

4. **Weekly Schedule Template**
   - How to split time between subjects
   - Practice vs theory balance

5. **Milestones & Checkpoints**
   - How to know you're progressing
   - Skills to demonstrate

Be specific and actionable. Include estimated weeks/months for each phase."""

    try:
        response = await call_jeeves(prompt, "encouraging", current_level)
        
        total_curriculum_hours = (
            JEEVES_KNOWLEDGE_BASE['physics']['total_hours'] +
            JEEVES_KNOWLEDGE_BASE['math']['total_hours'] +
            JEEVES_KNOWLEDGE_BASE['cs']['total_hours']
        )
        
        return {
            "goal": goal,
            "current_level": current_level,
            "hours_per_week": hours_per_week,
            "study_path": response,
            "total_curriculum_available": f"{total_curriculum_hours} hours",
            "estimated_journey": f"~{total_curriculum_hours // hours_per_week} weeks to complete everything",
            "jeeves_encouragement": "Remember, consistency beats intensity. Let's build your skills together!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
