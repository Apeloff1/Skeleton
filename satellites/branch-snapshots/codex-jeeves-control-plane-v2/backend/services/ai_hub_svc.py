"""
services/ai_hub_svc.py — AIHub service.

Extracted from server.py (Feb 2026 Phase-7). The class needs the
``LLMProvider`` enum from server.py, but to avoid a circular import we
defer the lookup until first instantiation via a small bootstrap
function. Server.py keeps a back-compat shim so existing callers continue
to work.

LLM keys are read from ``EMERGENT_LLM_KEY`` (universal Emergent key),
which is the same source the original implementation used.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import List


def _llm_provider_enum():
    """Lazy import of the LLMProvider enum from server.py.

    Required because the enum is currently still owned by server.py.
    Calling this at request time avoids any boot-order issues.
    """
    from server import LLMProvider  # lazy
    return LLMProvider


def _llm_chat():
    """Lazy import of LlmChat / UserMessage from emergentintegrations.

    Same lazy-import pattern keeps the module load fast even if the
    integrations library isn't yet on the path during tests.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # lazy
    return LlmChat, UserMessage


class AIHubService:
    """Self-evolving AI hub for state-of-the-art expansion suggestions."""

    def __init__(self):
        self.api_key = os.environ.get("EMERGENT_LLM_KEY")
        LLMProvider  = _llm_provider_enum()
        self.providers = {
            LLMProvider.OPENAI:    {"model": "gpt-4o",                    "available": True},
            LLMProvider.ANTHROPIC: {"model": "claude-sonnet-4-20250514",  "available": True},
            LLMProvider.GOOGLE:    {"model": "gemini-2.0-flash",          "available": True},
            LLMProvider.GROK:      {"model": "grok-3",                   "available": False},
        }

    async def suggest_features(self, context: dict) -> List[dict]:
        """AI-powered feature suggestions based on usage patterns."""
        if not self.api_key:
            return self._get_default_suggestions()
        try:
            LlmChat, UserMessage = _llm_chat()
            chat = LlmChat(
                api_key    = self.api_key,
                session_id = f"codedock-suggest-{uuid.uuid4().hex[:8]}",
                system_message=(
                    "You are an expert compiler and IDE feature analyst. "
                    "Based on the user's coding patterns and current feature set, "
                    "suggest innovative features that would enhance their development experience. "
                    "Focus on: 1) Productivity improvements 2) Code quality enhancements "
                    "3) Learning opportunities 4) Advanced compilation features 5) Integration possibilities. "
                    "Return suggestions as JSON array with: id, name, description, category, impact, implementation_difficulty"
                ),
            ).with_model("openai", "gpt-4o")
            response = await chat.send_message(UserMessage(text=(
                f"User context:\n"
                f"- Languages used: {context.get('languages', ['python'])}\n"
                f"- Features used: {context.get('features_used', [])}\n"
                f"- Skill level: {context.get('skill_level', 'intermediate')}\n"
                f"- Current installed packs: {context.get('installed_packs', [])}\n\n"
                "Suggest 5 innovative features they should add to their CodeDock IDE."
            )))
            try:
                import json
                matches = re.findall(r"\[[\s\S]*?\]", response)
                if matches:
                    return json.loads(matches[0])
            except Exception:
                pass
            return self._get_default_suggestions()
        except Exception:
            return self._get_default_suggestions()

    def _get_default_suggestions(self) -> List[dict]:
        return [
            {"id": "smart_completion",       "name": "AI Smart Completion",      "description": "Context-aware code completion powered by multiple LLMs",            "category": "productivity",  "impact": "high",     "implementation_difficulty": "medium"},
            {"id": "code_review_bot",        "name": "Automated Code Review",    "description": "AI-powered code review with security and performance insights",     "category": "quality",       "impact": "high",     "implementation_difficulty": "medium"},
            {"id": "interactive_debugger",   "name": "Visual Debugger",          "description": "Step-through debugging with variable inspection",                  "category": "debugging",     "impact": "critical", "implementation_difficulty": "high"},
            {"id": "performance_profiler",   "name": "Real-time Profiler",       "description": "CPU and memory profiling with flame graphs",                       "category": "performance",   "impact": "high",     "implementation_difficulty": "high"},
            {"id": "collaborative_editing",  "name": "Enhanced Collaboration",   "description": "Video chat and screen sharing during pair programming",            "category": "collaboration", "impact": "medium",   "implementation_difficulty": "high"},
        ]

    async def query_sota(self, domain: str) -> dict:
        """Query for state-of-the-art developments in a domain."""
        if not self.api_key:
            return {"status": "offline", "suggestions": []}
        try:
            LlmChat, UserMessage = _llm_chat()
            chat = LlmChat(
                api_key    = self.api_key,
                session_id = f"codedock-sota-{uuid.uuid4().hex[:8]}",
                system_message=(
                    "You are a cutting-edge technology analyst specializing in programming languages, "
                    "compilers, and developer tools. Provide the latest state-of-the-art developments "
                    "and recommendations."
                ),
            ).with_model("openai", "gpt-4o")
            response = await chat.send_message(UserMessage(text=(
                f"What are the latest state-of-the-art developments in {domain}?\n"
                "Include: 1) Latest technologies and frameworks 2) Best practices in 2025/2026 "
                "3) Emerging trends 4) Recommended tools and libraries 5) Performance optimization techniques. "
                "Be specific and actionable."
            )))
            return {
                "status":    "success",
                "domain":    domain,
                "analysis":  response,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def auto_implement_feature(self, feature_spec: dict) -> dict:
        """Generate implementation plan for a new feature."""
        if not self.api_key:
            return {"status": "offline"}
        try:
            LlmChat, UserMessage = _llm_chat()
            chat = LlmChat(
                api_key    = self.api_key,
                session_id = f"codedock-impl-{uuid.uuid4().hex[:8]}",
                system_message=(
                    "You are an expert software architect. Generate detailed implementation plans "
                    "for new IDE features including: 1) Architecture design 2) API endpoints needed "
                    "3) UI components 4) Data models 5) Integration points 6) Testing strategy."
                ),
            ).with_model("openai", "gpt-4o")
            response = await chat.send_message(UserMessage(text=(
                f"Generate an implementation plan for this feature:\n\n"
                f"Name: {feature_spec.get('name')}\n"
                f"Description: {feature_spec.get('description')}\n"
                f"Category: {feature_spec.get('category')}\n\n"
                "Provide a complete implementation roadmap."
            )))
            return {
                "status":                "success",
                "feature":               feature_spec.get("name"),
                "implementation_plan":   response,
                "estimated_complexity":  feature_spec.get("implementation_difficulty", "medium"),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# We can't construct the singleton at import time because it needs
# server.LLMProvider, which causes a circular import. Instead, expose a
# lazy property that constructs on first access.
_AI_HUB_SINGLETON: AIHubService | None = None


def get_ai_hub() -> AIHubService:
    """Return the lazily-instantiated AIHub singleton."""
    global _AI_HUB_SINGLETON
    if _AI_HUB_SINGLETON is None:
        _AI_HUB_SINGLETON = AIHubService()
    return _AI_HUB_SINGLETON


__all__ = ["AIHubService", "get_ai_hub"]
