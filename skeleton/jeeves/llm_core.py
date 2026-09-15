"""
Skeleton Jeeves — Conversational AI orchestration layer (provider-backed,
with memory matrices: SAM, CLOM, KREM, KAG citations, and the ResponseCycle)

JeevesCore delegates response generation to an LLM provider while the
matrices observe every turn:
- SAM builds a co-occurrence graph used to expand queries
- CLOM tracks per-intent outcome rates
- KREM tracks per-concept retention with spaced decay
- CitationEngine grounds replies in knowledge-graph facts
- ResponseCycle distills each reply into work orders between turns
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.jeeves.citations import CitationEngine
from skeleton.jeeves.matrices_llm import (
    CompressedLearnedOutcomeModel,
    KnowledgeRetentionMatrix,
    SemanticAssociationMap,
)


MAX_INPUT_CHARS = 32_000


class SessionMode(Enum):
    TUTORING = "tutoring"
    CO_CODING = "co_coding"
    TACTICAL = "tactical"
    BUILDER = "builder"
    CORTEX = "cortex"
    CREATIVE = "creative"
    ANALYTICAL = "analytical"
    DEBUG = "debug"


def _normalise_mode(mode: Any) -> SessionMode:
    """Normalize sibling/legacy enums and strings onto JeevesCore's enum.

    The HTTP API historically imported ``SessionMode`` from ``jeeves.core``
    while the provider-backed JeevesCore owns the enum in this module. Enum
    instances from different classes do not compare equal even when their
    values match, which silently disabled mode-specific system prompts.
    """
    if isinstance(mode, SessionMode):
        return mode
    raw = getattr(mode, "value", mode)
    try:
        return SessionMode(str(raw))
    except (TypeError, ValueError):
        return SessionMode.TUTORING


@dataclass
class Turn:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    session_id: str
    user_id: str
    mode: SessionMode
    turns: List[Turn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_turn(self, role: str, content: str, **kwargs) -> Turn:
        turn = Turn(role=role, content=content, metadata=kwargs)
        self.turns.append(turn)
        return turn

    def context_window(self, max_turns: int = 10) -> List[str]:
        return [t.content for t in self.turns[-max_turns:]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "mode": self.mode.value,
            "turn_count": len(self.turns),
            "created_at": self.created_at,
        }


class MemoryManager:
    def __init__(self, max_sessions: int = 1000):
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, List[str]] = {}
        self._max_sessions = max_sessions
        self._stats = {"created": 0, "retrieved": 0}

    def create_session(self, user_id: str, mode: SessionMode = SessionMode.TUTORING) -> Session:
        session = Session(session_id=str(uuid.uuid4())[:12], user_id=user_id, mode=mode)
        self._sessions[session.session_id] = session
        self._user_sessions.setdefault(user_id, []).append(session.session_id)
        self._stats["created"] += 1
        if len(self._sessions) > self._max_sessions:
            oldest = min(self._sessions.keys(), key=lambda s: self._sessions[s].created_at)
            evicted = self._sessions.pop(oldest)
            history = self._user_sessions.get(evicted.user_id)
            if history is not None:
                self._user_sessions[evicted.user_id] = [sid for sid in history if sid != oldest]
                if not self._user_sessions[evicted.user_id]:
                    del self._user_sessions[evicted.user_id]
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        self._stats["retrieved"] += 1
        return self._sessions.get(session_id)

    def get_user_history(self, user_id: str, limit: int = 10) -> List[Session]:
        ids = self._user_sessions.get(user_id, [])[-limit:]
        return [self._sessions[sid] for sid in ids if sid in self._sessions]

    def add_to_session(self, session_id: str, role: str, content: str, **kwargs) -> Optional[Turn]:
        session = self._sessions.get(session_id)
        return session.add_turn(role, content, **kwargs) if session else None

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "active_sessions": len(self._sessions), "users": len(self._user_sessions)}


MODE_SYSTEM_PROMPTS: Dict[SessionMode, str] = {
    SessionMode.TUTORING: "You are a patient tutor. Explain step by step.",
    SessionMode.CO_CODING: "You are a co-coding partner. Review, explain, and keep the learner in control.",
    SessionMode.TACTICAL: "You are a tactical systems advisor. Prioritize the highest-impact next action.",
    SessionMode.BUILDER: "You are a builder. Turn goals into concrete architecture and implementation steps.",
    SessionMode.CORTEX: "You are a systems reasoning cortex. Integrate evidence across subsystems before answering.",
    SessionMode.CREATIVE: "You are a creative collaborator. Offer vivid ideas.",
    SessionMode.ANALYTICAL: "You are a precise analyst. Be structured and cite evidence.",
    SessionMode.DEBUG: "You are a debugging assistant. Find the root cause.",
}


class JeevesCore:
    """Conversational orchestration with pluggable LLM backends, memory
    matrices, knowledge-graph citations, and the between-turns ResponseCycle."""

    def __init__(self, bus: Optional[EventBus] = None, retriever: Optional[Any] = None,
                 provider: Optional[Any] = None, cycle: Optional[Any] = None):
        self._bus = bus
        self._memory = MemoryManager()
        self._tools: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._stats = {"interactions": 0, "tool_calls": 0}

        # Memory matrices
        self.sam = SemanticAssociationMap()
        self.clom = CompressedLearnedOutcomeModel()
        self.krem = KnowledgeRetentionMatrix()

        # Citations: grounded in the retriever's KAG plane when available
        kag = None
        if retriever is not None:
            planes = getattr(retriever, "_planes", None) or {}
            kag = planes.get("kag")
            if kag is None and hasattr(retriever, "graph"):
                kag = retriever
        self.citations = CitationEngine(kag=kag)

        # ResponseCycle: distills replies into work orders between turns
        self._cycle = cycle

        if provider is not None:
            self._provider = provider
        else:
            from skeleton.jeeves.providers import get_provider
            self._provider = get_provider(retriever=retriever)

    def register_tool(self, name: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        self._tools[name] = handler

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "name", "unknown")

    def open_session(self, user_id: str, mode: SessionMode = SessionMode.TUTORING) -> Session:
        normalized_user = str(user_id or "").strip() or "anonymous"
        normalized_mode = _normalise_mode(mode)
        session = self._memory.create_session(normalized_user, normalized_mode)
        if self._bus:
            self._bus.emit("jeeves.session.opened", {
                "session_id": session.session_id,
                "user_id": normalized_user,
                "mode": normalized_mode.value,
            })
        return session

    def ask(self, session_id: str, input_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session = self._memory.get_session(session_id)
        if not session:
            return {"error": "Session not found", "session_id": session_id}

        text = str(input_text or "").strip()
        if not text:
            return {"error": "Input must be non-empty", "session_id": session_id}
        if len(text) > MAX_INPUT_CHARS:
            return {
                "error": "Input too large",
                "session_id": session_id,
                "max_input_chars": MAX_INPUT_CHARS,
            }

        safe_context = context if isinstance(context, dict) else {}
        session.add_turn("user", text, **safe_context)

        # Matrices observe the input
        self.sam.observe(text)
        for term in self.sam._terms(text):
            self.krem.observe(term)

        # SAM expansion enriches the prompt with associated concepts
        expansions = self.sam.expand(text)
        system = MODE_SYSTEM_PROMPTS.get(session.mode, "")
        prompt = f"{system}\n\n{text}" if system else text
        if expansions:
            prompt += f"\n\nRelated concepts: {', '.join(expansions[:5])}"

        # Citations: graph facts supporting this query (+ SAM context)
        cited = self.citations.cite(text, context_terms=expansions)
        if cited:
            prompt += "\n\nKnown facts:\n" + "\n".join(f"- {c.render()}" for c in cited[:5])

        start = time.time()
        provider_error = None
        try:
            content = self._provider.complete(prompt, context=session.context_window())
            success = True
        except Exception as exc:
            # Provider exceptions can contain API keys, URLs, raw payloads, or
            # other deployment details. Keep the client response deterministic
            # and expose only the exception class for operator diagnostics.
            content = "[provider unavailable]"
            provider_error = type(exc).__name__
            success = False
        latency_ms = (time.time() - start) * 1000

        # CLOM tracks the outcome for this intent (= session mode)
        self.clom.observe(session.mode.value, success, latency_ms)

        # Matrices observe the response too (assistant language feeds SAM)
        self.sam.observe(content)

        tools_used = [t for t in self._tools if t in text.lower()]
        for tool in tools_used:
            try:
                self._tools[tool]({"input": text, "session": session.to_dict()})
                self._stats["tool_calls"] += 1
            except Exception:
                pass

        # Context fabric: consume the interjection earned last turn, then
        # run the between-turns cycle on this reply (distill → execute → guide)
        cycle_report = None
        interjection = None
        if self._cycle is not None:
            interjection = self._cycle.before_reply()
            if interjection:
                content = interjection + "\n\n" + content
            token_count = max(1, len(content) // 4)  # rough token estimate
            cycle_report = self._cycle.after_reply(content, token_count)

        turn_metadata: Dict[str, Any] = {
            "tools_used": tools_used,
            "provider": self.provider_name,
            "citations": len(cited),
            "success": success,
        }
        if provider_error:
            turn_metadata["provider_error"] = provider_error
        session.add_turn("assistant", content, **turn_metadata)
        self._stats["interactions"] += 1

        if self._bus:
            event = {
                "session_id": session_id,
                "provider": self.provider_name,
                "input_length": len(text),
                "response_length": len(content),
                "sam_expansions": len(expansions),
                "citations": len(cited),
                "latency_ms": latency_ms,
                "success": success,
            }
            if provider_error:
                event["provider_error"] = provider_error
            self._bus.emit("jeeves.interaction", event)

        result: Dict[str, Any] = {
            "content": content,
            "tools": tools_used,
            "mode": session.mode.value,
            "provider": self.provider_name,
            "expansions": expansions[:5],
            "citations": [c.to_dict() for c in cited],
            "latency_ms": round(latency_ms, 1),
        }
        if provider_error:
            result["provider_error"] = provider_error
        if interjection:
            result["interjection"] = interjection
        if cycle_report is not None:
            result["cycle"] = cycle_report.to_dict()
            if cycle_report.oracle_shift:
                result["oracle"] = cycle_report.oracle_shift
        return result

    def matrices(self) -> Dict[str, Any]:
        """Snapshot all three memory matrices (API /jeeves/matrices surface)."""
        return {
            "sam": self.sam.snapshot(),
            "clom": self.clom.snapshot(),
            "krem": self.krem.snapshot(),
        }

    def refresh_due(self) -> List[str]:
        """Concepts due for refresh per KREM (pairs with RepetitionScheduler)."""
        return self.krem.due()

    def review_code(self, session_id: str, code: str) -> Dict[str, Any]:
        session = self._memory.get_session(session_id)
        if not session:
            return {"error": "Session not found"}
        issues = []
        if "import *" in code:
            issues.append("Avoid wildcard imports")
        if "TODO" in code:
            issues.append("Address TODO comments")
        if len(code) > 1000:
            issues.append("Consider breaking into smaller functions")
        return {"issues": issues, "issue_count": len(issues), "session_id": session_id}

    def bind_era(self, era: str) -> Dict[str, Any]:
        return {"era": era, "primary_dps": ["sword", "bow", "magic"], "status": "bound"}

    def advise(self, session_id: str, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "advice": "Monitor system health regularly",
            "telemetry_summary": {"keys": list(telemetry.keys())},
            "session_id": session_id,
        }

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "provider": self.provider_name,
            "active_sessions": self._memory.stats()["active_sessions"],
            "tools_available": len(self._tools),
            "citations": self.citations.stats(),
            "cycle": self._cycle.stats() if self._cycle is not None else None,
            "matrices": {
                "sam": self.sam.stats(),
                "clom": self.clom.stats(),
                "krem": self.krem.stats(),
            },
        }
