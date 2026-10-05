"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  REAL-TIME COLLABORATION & LIVE CODING - April 2026 SOTA                     ║
║  AI Pair Programming, Live Sessions, Collaborative Debugging                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import os
import uuid

router = APIRouter(prefix="/collab", tags=["Collaboration"])

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False

EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY", "")

# ============================================================================
# SESSION STORAGE (In production, use Redis)
# ============================================================================

active_sessions: Dict[str, Dict] = {}

# ============================================================================
# REQUEST MODELS
# ============================================================================

class PairProgramRequest(BaseModel):
    code: str
    language: str = "python"
    task: str
    ai_role: str = "copilot"  # copilot, driver, navigator, reviewer
    session_id: Optional[str] = None

class LiveSuggestionRequest(BaseModel):
    code: str
    cursor_line: int
    cursor_col: int
    language: str = "python"
    recent_changes: List[str] = []
    session_id: Optional[str] = None

class CollabDebugRequest(BaseModel):
    code: str
    error: str
    language: str = "python"
    session_id: Optional[str] = None
    include_fix: bool = True

class CodeExplainRequest(BaseModel):
    code: str
    language: str = "python"
    explain_level: str = "detailed"  # brief, detailed, eli5
    highlight_lines: List[int] = []

class RefactorSuggestionRequest(BaseModel):
    code: str
    language: str = "python"
    focus_areas: List[str] = []  # readability, performance, security, modern

# ============================================================================
# HELPER
# ============================================================================

async def call_llm(system: str, prompt: str) -> str:
    if not LLM_AVAILABLE or not EMERGENT_KEY:
        return "LLM not available"
    try:
        chat = LlmChat(api_key=EMERGENT_KEY, system_message=system).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        return f"Error: {str(e)}"

# ============================================================================
# AI PAIR PROGRAMMING
# ============================================================================

@router.post("/pair-program")
async def ai_pair_programming(request: PairProgramRequest):
    """AI pair programming with different roles"""
    
    role_prompts = {
        "copilot": "You are a coding copilot. Help complete the code, suggest next steps, and provide inline assistance. Be concise but helpful.",
        "driver": "You are the driver in pair programming. Write the code while the user navigates. Implement their ideas efficiently.",
        "navigator": "You are the navigator. Guide the user's coding, suggest approaches, catch errors early, think about the big picture.",
        "reviewer": "You are a live code reviewer. Comment on code as it's written, suggest improvements, catch bugs immediately."
    }
    
    session_id = request.session_id or str(uuid.uuid4())[:8]
    
    result = await call_llm(
        role_prompts.get(request.ai_role, role_prompts["copilot"]),
        f"""Task: {request.task}

Current code ({request.language}):
```{request.language}
{request.code}
```

As the {request.ai_role}, provide your contribution."""
    )
    
    # Store session
    active_sessions[session_id] = {
        "role": request.ai_role,
        "language": request.language,
        "last_code": request.code,
        "last_active": datetime.utcnow().isoformat()
    }
    
    return {
        "session_id": session_id,
        "ai_role": request.ai_role,
        "response": result,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# LIVE SUGGESTIONS
# ============================================================================

@router.post("/live-suggest")
async def live_code_suggestions(request: LiveSuggestionRequest):
    """Real-time code suggestions as you type"""
    
    # Get context around cursor
    lines = request.code.split('\n')
    context_start = max(0, request.cursor_line - 10)
    context_end = min(len(lines), request.cursor_line + 5)
    context = '\n'.join(lines[context_start:context_end])
    
    result = await call_llm(
        "You are a real-time coding assistant. Provide immediate, contextual suggestions. Be extremely concise. Output 1-3 suggestions max.",
        f"""Code context ({request.language}):
```{request.language}
{context}
```

Cursor at line {request.cursor_line}, column {request.cursor_col}
Recent changes: {request.recent_changes[-3:] if request.recent_changes else 'None'}

Provide quick suggestions (code completions, fixes, or improvements)."""
    )
    
    return {
        "suggestions": result,
        "cursor": {"line": request.cursor_line, "col": request.cursor_col},
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# COLLABORATIVE DEBUGGING
# ============================================================================

@router.post("/collab-debug")
async def collaborative_debugging(request: CollabDebugRequest):
    """AI-assisted collaborative debugging session"""
    
    result = await call_llm(
        "You are a debugging partner. Analyze errors, explain root causes clearly, and provide fixes. Think step by step.",
        f"""Debug this {request.language} code:

```{request.language}
{request.code}
```

Error:
```
{request.error}
```

Provide:
1. Root cause analysis
2. Step-by-step explanation
3. {"Fixed code" if request.include_fix else "Fix approach"}
4. How to prevent this in future"""
    )
    
    return {
        "debug_analysis": result,
        "error_type": "analyzed",
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# LIVE CODE EXPLANATION
# ============================================================================

@router.post("/explain-live")
async def live_code_explanation(request: CodeExplainRequest):
    """Real-time code explanation as you navigate"""
    
    level_prompts = {
        "brief": "Explain very briefly in 1-2 sentences.",
        "detailed": "Explain thoroughly with examples.",
        "eli5": "Explain like I'm 5 years old, use simple analogies."
    }
    
    result = await call_llm(
        f"You explain code clearly. {level_prompts.get(request.explain_level, level_prompts['detailed'])}",
        f"""Explain this {request.language} code:

```{request.language}
{request.code}
```

{f"Focus on lines: {request.highlight_lines}" if request.highlight_lines else "Explain the entire code."}"""
    )
    
    return {
        "explanation": result,
        "level": request.explain_level,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# INSTANT REFACTOR SUGGESTIONS
# ============================================================================

@router.post("/refactor-suggest")
async def instant_refactor_suggestions(request: RefactorSuggestionRequest):
    """Get instant refactoring suggestions"""
    
    focus = request.focus_areas if request.focus_areas else ["readability", "performance"]
    
    result = await call_llm(
        "You are a refactoring expert. Suggest specific, actionable improvements. Show before/after code snippets.",
        f"""Suggest refactorings for this {request.language} code:

```{request.language}
{request.code}
```

Focus areas: {focus}

For each suggestion:
1. What to change
2. Why (benefit)
3. Before/after code snippet"""
    )
    
    return {
        "suggestions": result,
        "focus_areas": focus,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

@router.get("/sessions")
async def get_active_sessions():
    """Get all active collaboration sessions"""
    return {
        "sessions": active_sessions,
        "count": len(active_sessions)
    }

@router.delete("/session/{session_id}")
async def end_session(session_id: str):
    """End a collaboration session"""
    if session_id in active_sessions:
        del active_sessions[session_id]
        return {"status": "ended", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")

@router.get("/info")
async def get_collab_info():
    """Get collaboration features info"""
    return {
        "name": "CodeDock Live Collaboration",
        "version": "11.3.0",
        "features": [
            {"id": "pair-program", "name": "AI Pair Programming", "roles": ["copilot", "driver", "navigator", "reviewer"]},
            {"id": "live-suggest", "name": "Live Suggestions", "desc": "Real-time code suggestions"},
            {"id": "collab-debug", "name": "Collaborative Debug", "desc": "Debug together with AI"},
            {"id": "explain-live", "name": "Live Explanation", "desc": "Understand code in real-time"},
            {"id": "refactor-suggest", "name": "Instant Refactor", "desc": "Quick refactoring suggestions"},
        ],
        "active_sessions": len(active_sessions)
    }
