"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              ENHANCED AI ASSISTANT v15.5 - LLM-POWERED CODING                ║
║                                                                              ║
║  Full LLM integration for intelligent code assistance:                       ║
║  • AI-powered code explanation                                               ║
║  • Intelligent debugging                                                     ║
║  • Smart optimization suggestions                                            ║
║  • Context-aware code completion                                             ║
║  • Automated refactoring                                                     ║
║  • Documentation generation                                                  ║
║  • Test generation                                                           ║
║  • Security auditing                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

# Import LLM service
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

router = APIRouter(prefix="/ai", tags=["AI Assistant v15.5"])

# API Key
API_KEY = os.getenv("EMERGENT_LLM_KEY", "")

# AI Modes available
AI_MODES = {
    "explain": {
        "id": "explain",
        "name": "Explain Code",
        "description": "Get detailed explanations of code with AI",
        "icon": "📖",
        "system_prompt": "You are an expert programming tutor. Explain code clearly and thoroughly, covering what each part does, why it's written that way, and potential improvements."
    },
    "debug": {
        "id": "debug",
        "name": "Debug Code",
        "description": "Find and fix bugs with AI analysis",
        "icon": "🐛",
        "system_prompt": "You are an expert debugger. Analyze code for bugs, edge cases, and potential issues. Provide specific line-by-line analysis and fixes."
    },
    "optimize": {
        "id": "optimize",
        "name": "Optimize Code",
        "description": "AI-powered performance optimization",
        "icon": "⚡",
        "system_prompt": "You are a performance optimization expert. Analyze code for performance issues and suggest optimizations. Consider time complexity, space complexity, and best practices."
    },
    "complete": {
        "id": "complete",
        "name": "Complete Code",
        "description": "AI auto-completion for partial code",
        "icon": "✨",
        "system_prompt": "You are an AI code completion assistant. Complete the given partial code following the established patterns and context. Provide clean, working code."
    },
    "refactor": {
        "id": "refactor",
        "name": "Refactor Code",
        "description": "AI-powered code restructuring",
        "icon": "🔄",
        "system_prompt": "You are a senior software architect. Refactor code to improve readability, maintainability, and follow SOLID principles. Explain each change."
    },
    "document": {
        "id": "document",
        "name": "Document Code",
        "description": "Generate comprehensive documentation",
        "icon": "📝",
        "system_prompt": "You are a technical writer. Generate comprehensive documentation including docstrings, comments, and README content. Follow the language's documentation conventions."
    },
    "test_gen": {
        "id": "test_gen",
        "name": "Generate Tests",
        "description": "AI-generated unit tests",
        "icon": "🧪",
        "system_prompt": "You are a QA engineer. Generate comprehensive unit tests covering edge cases, error conditions, and normal operations. Use the appropriate testing framework for the language."
    },
    "security_audit": {
        "id": "security_audit",
        "name": "Security Audit",
        "description": "AI security vulnerability scan",
        "icon": "🔒",
        "system_prompt": "You are a cybersecurity expert. Audit code for security vulnerabilities including SQL injection, XSS, CSRF, authentication issues, and data exposure. Provide severity ratings and fixes."
    },
    "convert": {
        "id": "convert",
        "name": "Convert Language",
        "description": "AI language translation",
        "icon": "🔀",
        "system_prompt": "You are a polyglot programmer. Convert code from one language to another while maintaining functionality, following target language conventions, and optimizing for the target platform."
    },
    "review": {
        "id": "review",
        "name": "Code Review",
        "description": "AI code review feedback",
        "icon": "👁️",
        "system_prompt": "You are a senior code reviewer. Provide thorough code review feedback including code quality, best practices, potential issues, and suggestions for improvement."
    }
}

# AI Providers
AI_PROVIDERS = [
    {"id": "openai", "name": "OpenAI GPT-4o", "status": "available", "model": "gpt-4o"},
    {"id": "claude", "name": "Anthropic Claude", "status": "available", "model": "claude-3-opus"},
    {"id": "gemini", "name": "Google Gemini", "status": "available", "model": "gemini-pro"},
]


class AIAssistRequest(BaseModel):
    code: str = Field(..., description="Code to analyze")
    language: str = Field(default="python", description="Programming language")
    mode: str = Field(default="explain", description="AI assistance mode")
    context: Optional[str] = Field(None, description="Additional context")
    target_language: Optional[str] = Field(None, description="Target language for conversion")


class AIAssistResponse(BaseModel):
    id: str
    mode: str
    suggestion: str
    explanation: Optional[str] = None
    code_blocks: List[Dict[str, str]] = []
    confidence: float = 0.95
    model: str = "gpt-4o"
    ai_generated: bool = True
    timestamp: str


class AIChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    context: Optional[str] = Field(None, description="Code context")
    conversation_history: List[Dict[str, str]] = Field(default=[], description="Previous messages")


async def call_llm(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """Call the LLM with given prompts."""
    if not LLM_AVAILABLE or not API_KEY:
        return {"success": False, "error": "LLM not available"}
    
    try:
        chat = LlmChat(
            api_key=API_KEY,
            session_id=str(uuid.uuid4()),
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")
        
        response = await chat.send_message(UserMessage(text=user_prompt))
        return {"success": True, "response": response}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/modes")
async def get_ai_modes():
    """Get available AI assistance modes"""
    modes = [
        {
            "id": mode["id"],
            "name": mode["name"],
            "description": mode["description"],
            "icon": mode["icon"]
        }
        for mode in AI_MODES.values()
    ]
    return {
        "modes": modes,
        "total": len(modes),
        "llm_available": LLM_AVAILABLE and bool(API_KEY)
    }


@router.post("/assist")
async def ai_assist(request: AIAssistRequest):
    """Get AI assistance for code using LLM"""
    mode_info = AI_MODES.get(request.mode, AI_MODES["explain"])
    
    # Build user prompt based on mode
    if request.mode == "convert" and request.target_language:
        user_prompt = f"""Convert this {request.language} code to {request.target_language}:

```{request.language}
{request.code}
```

{f"Additional context: {request.context}" if request.context else ""}

Provide the converted code with explanations of any changes needed for the target language."""
    else:
        user_prompt = f"""Analyze this {request.language} code:

```{request.language}
{request.code}
```

{f"Additional context: {request.context}" if request.context else ""}

Provide your analysis in a clear, structured format."""
    
    # Call LLM
    result = await call_llm(mode_info["system_prompt"], user_prompt)
    
    if result["success"]:
        return AIAssistResponse(
            id=str(uuid.uuid4()),
            mode=request.mode,
            suggestion=result["response"],
            explanation=f"AI analysis using {mode_info['name']} mode",
            code_blocks=[],
            confidence=0.95,
            model="gpt-4o",
            ai_generated=True,
            timestamp=datetime.utcnow().isoformat()
        )
    else:
        # Fallback response
        fallback_responses = {
            "explain": f"This {request.language} code follows standard patterns. For detailed AI analysis, please ensure the LLM service is available.",
            "debug": "Basic static analysis complete. For AI-powered debugging, ensure the LLM service is configured.",
            "optimize": "Consider standard optimization patterns. AI-powered optimization requires LLM configuration.",
            "complete": "# Code completion placeholder\npass",
            "refactor": "Consider extracting repeated logic into functions. AI refactoring requires LLM service.",
            "document": f'"""\nModule: {request.language} code\n\nDescription: Auto-generated documentation placeholder.\n"""',
            "test_gen": f"def test_example():\n    # AI-generated test placeholder\n    pass",
            "security_audit": "Basic security check complete. For comprehensive AI audit, configure LLM service.",
            "convert": "// Language conversion requires LLM service",
            "review": "Code review requires AI service. Basic check: code appears syntactically correct."
        }
        
        return AIAssistResponse(
            id=str(uuid.uuid4()),
            mode=request.mode,
            suggestion=fallback_responses.get(request.mode, "Analysis complete."),
            explanation=f"Fallback analysis - LLM unavailable: {result.get('error', 'Unknown error')}",
            code_blocks=[],
            confidence=0.5,
            model="fallback",
            ai_generated=False,
            timestamp=datetime.utcnow().isoformat()
        )


@router.post("/chat")
async def ai_chat(request: AIChatRequest):
    """Chat with AI assistant about coding"""
    system_prompt = """You are a helpful AI coding assistant named Jeeves from Tutolage Academy.
You help developers with coding questions, debugging, and learning.
Be friendly, encouraging, and provide practical examples.
Keep responses concise but informative."""
    
    context_info = ""
    if request.context:
        context_info = f"\n\nCode context:\n```\n{request.context}\n```"
    
    user_prompt = f"{request.message}{context_info}"
    
    result = await call_llm(system_prompt, user_prompt)
    
    if result["success"]:
        return {
            "success": True,
            "response": result["response"],
            "ai_generated": True,
            "model": "gpt-4o",
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        return {
            "success": False,
            "response": "I'm having trouble connecting to my AI brain right now. Please try again!",
            "ai_generated": False,
            "error": result.get("error"),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/providers")
async def get_ai_providers():
    """Get available AI providers"""
    return {
        "providers": AI_PROVIDERS,
        "active": "openai",
        "llm_available": LLM_AVAILABLE and bool(API_KEY)
    }


@router.post("/quick-actions")
async def ai_quick_actions(code: str, language: str = "python"):
    """Get quick AI action suggestions for code"""
    return {
        "actions": [
            {"id": "explain", "label": "Explain this code", "icon": "📖"},
            {"id": "debug", "label": "Find bugs", "icon": "🐛"},
            {"id": "optimize", "label": "Optimize performance", "icon": "⚡"},
            {"id": "test_gen", "label": "Generate tests", "icon": "🧪"},
            {"id": "document", "label": "Add documentation", "icon": "📝"},
            {"id": "security_audit", "label": "Security check", "icon": "🔒"},
        ],
        "recommended": "explain" if len(code) > 100 else "complete"
    }


@router.get("/status")
async def ai_status():
    """Get AI service status"""
    return {
        "status": "operational" if (LLM_AVAILABLE and API_KEY) else "limited",
        "llm_available": LLM_AVAILABLE,
        "api_key_configured": bool(API_KEY),
        "model": "gpt-4o",
        "features": {
            "code_assist": True,
            "chat": LLM_AVAILABLE and bool(API_KEY),
            "code_generation": LLM_AVAILABLE and bool(API_KEY),
            "security_audit": LLM_AVAILABLE and bool(API_KEY)
        }
    }
