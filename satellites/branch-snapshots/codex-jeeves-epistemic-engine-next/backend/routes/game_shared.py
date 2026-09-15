"""
GAME SHARED — Common utilities, DB connections, models, and helpers
shared across all game factory sub-routers.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
import os
import uuid
import json
from dotenv import load_dotenv

load_dotenv()

# LLM Integration
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
db = client[os.environ.get('DB_NAME', 'test_database')]

projects_collection = db.game_projects
build_steps_collection = db.game_build_steps
vault_collection = db.code_vault

EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY", "")


# =============================================================================
# LLM HELPER
# =============================================================================

async def call_llm(system_prompt: str, user_prompt: str, session_id: str = None) -> dict:
    """Call LLM with fallback to mock data."""
    if not LLM_AVAILABLE or not EMERGENT_KEY:
        return {"success": False, "response": None, "error": "LLM not available"}

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=session_id or str(uuid.uuid4()),
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=user_prompt))
        return {"success": True, "response": response, "error": None}
    except Exception as e:
        return {"success": False, "response": None, "error": str(e)}


def parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response."""
    if not text:
        return {}
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1]
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"raw_output": text}


def _extract_code_blocks(text: str) -> list:
    """Extract code blocks from markdown text."""
    if not text:
        return []
    blocks = []
    parts = text.split("```")
    for i in range(1, len(parts), 2):
        code = parts[i]
        lines = code.split("\n", 1)
        if len(lines) > 1 and not lines[0].strip().startswith("{"):
            code = lines[1]
        blocks.append(code.strip())
    return blocks


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CreateGameRequest(BaseModel):
    description: str
    genre: Optional[str] = None
    engine: Optional[str] = None
    features: Optional[List[str]] = None
    art_style: Optional[str] = None
    target_platform: Optional[str] = "PC"
    user_id: str = "default_user"

class BuildStepRequest(BaseModel):
    project_id: str
    step_number: Optional[int] = None
    user_id: str = "default_user"

class CompileRequest(BaseModel):
    project_id: str
    user_id: str = "default_user"

class GenreChatRequest(BaseModel):
    genre_id: str
    specialist_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class DesignChatRequest(BaseModel):
    agent_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class TechnicalChatRequest(BaseModel):
    agent_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class FactoryChatRequest(BaseModel):
    agent_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class RosterChatRequest(BaseModel):
    agent_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class AcademicChatRequest(BaseModel):
    agent_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class HierarchyChatRequest(BaseModel):
    agent_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class CommandChatRequest(BaseModel):
    agent_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class ExpansionChatRequest(BaseModel):
    agent_id: str
    division: str = "alpha"
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class CourtGuardChatRequest(BaseModel):
    agent_id: str
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class AccuracyChatRequest(BaseModel):
    agent_id: str
    division: str = "alpha"
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class AccuracyReviewRequest(BaseModel):
    agent_id: str
    division: str = "alpha"
    target_output: str
    game_context: str = ""

class ShadowReviewRequest(BaseModel):
    agent_id: str
    target_output: str
    game_context: str = ""

class GhostReviewRequest(BaseModel):
    agent_id: str
    target_output: str
    game_context: str = ""

class AngelReviewRequest(BaseModel):
    agent_id: str
    target_output: str
    game_context: str = ""

class HolodeckRenderRequest(BaseModel):
    team_name: str
    team_output: str
    game_context: str = ""

class HolodeckChatRequest(BaseModel):
    message: str
    game_description: str = ""
    session_id: Optional[str] = None

class CompetitorAnalysisRequest(BaseModel):
    target_game: str
    our_game_description: str = ""
    analysis_depth: str = "comprehensive"
