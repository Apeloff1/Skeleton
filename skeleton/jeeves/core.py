"""Jeeves core: system laws, session orchestration, co-coding mode.

Jeeves is the tutor persona that fronts the platform. The core owns session
lifecycle, enforces the system laws (pedagogy-first, honesty, safety), and
switches into co-coding mode when the learner wants to build rather than be
taught. LLM access is injected; without a backend, Jeeves answers from its
local scaffolding responder.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from skeleton.kernel.errors import SessionError
from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import SessionId, UserId

SYSTEM_LAWS: tuple[str, ...] = (
    "Teach, don't just answer: every response must advance understanding.",
    "Never fabricate: say 'I don't know' rather than invent.",
    "Adapt to the learner: pace, depth, and register follow the learner model.",
    "In co-coding mode, the learner drives; Jeeves reviews and explains.",
    "Safety first: refuse harmful content and redirect constructively.",
)


class SessionMode(str, Enum):
    TUTORING = "tutoring"
    CO_CODING = "co_coding"
    TACTICAL = "tactical"
    BUILDER = "builder"
    CORTEX = "cortex"


@dataclass
class Turn:
    role: str  # "learner" | "jeeves"
    content: str
    at: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    user_id: str
    mode: SessionMode = SessionMode.TUTORING
    turns: list[Turn] = field(default_factory=list)
    opened_at: float = field(default_factory=time.time)
    closed_at: float | None = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def add_turn(self, role: str, content: str) -> Turn:
        if not self.is_open:
            raise SessionError("cannot add a turn to a closed session",
                               context={"session_id": self.session_id})
        turn = Turn(role=role, content=content)
        self.turns.append(turn)
        return turn


ResponderFn = Callable[[str, list[Turn], dict[str, Any]], str]


def _local_responder(message: str, history: list[Turn], context: dict[str, Any]) -> str:
    """Fallback responder: Socratic scaffolding without an LLM backend."""
    topic = message.strip().rstrip("?")[:80]
    hints = context.get("hints") or []
    prefix = "Let's work through this together. " if history else "Good question. "
    scaffold = f"On '{topic}': start by stating what you already know about it."
    if hints:
        scaffold += f" Hint: {hints[0]}."
    scaffold += " Then tell me where your understanding gets shaky, and we'll build from there."
    return prefix + scaffold


class Jeeves:
    """The tutor brain: sessions, laws, co-coding."""

    def __init__(self, bus: EventBus | None = None,
                 responder: ResponderFn | None = None,
                 *, max_turns: int = 200) -> None:
        self._bus = bus or EventBus()
        self._responder = responder or _local_responder
        self._max_turns = max_turns
        self._sessions: dict[str, Session] = {}
        self._brain = None  # lazy TacticalBrain
        self._cortex = None  # lazy JeevesCortex — the model in training
        self.era = "extraction_now"
        self.last_plan = None

    @property
    def laws(self) -> tuple[str, ...]:
        return SYSTEM_LAWS

    def open_session(self, user_id: str | UserId, *, mode: SessionMode = SessionMode.TUTORING) -> Session:
        session = Session(session_id=str(SessionId.new()), user_id=str(user_id), mode=mode)
        self._sessions[session.session_id] = session
        self._bus.emit("jeeves.session.opened",
                       {"session_id": session.session_id, "mode": mode.value})
        return session

    def close_session(self, session_id: str) -> Session:
        session = self._get(session_id)
        if session.is_open:
            session.closed_at = time.time()
            self._bus.emit("jeeves.session.closed",
                           {"session_id": session_id, "turns": len(session.turns)})
        return session

    def set_mode(self, session_id: str, mode: SessionMode) -> Session:
        session = self._get(session_id)
        if not session.is_open:
            raise SessionError("session is closed", context={"session_id": session_id})
        session.mode = mode
        self._bus.emit("jeeves.session.mode_changed",
                       {"session_id": session_id, "mode": mode.value})
        return session

    def ask(self, session_id: str, message: str, *, context: dict[str, Any] | None = None) -> str:
        """Take a learner turn, produce the tutor's reply."""
        if not message or not message.strip():
            raise SessionError("message must be non-empty")
        session = self._get(session_id)
        if len(session.turns) >= self._max_turns:
            raise SessionError("session turn limit reached",
                               context={"session_id": session_id, "max_turns": self._max_turns})
        session.add_turn("learner", message)
        ctx = dict(context or {})
        ctx["mode"] = session.mode.value
        if session.mode in (SessionMode.TACTICAL, SessionMode.BUILDER):
            tel = ctx.get("telemetry") or {}
            reply = self._brain_get().recommend_next(tel).text
        elif session.mode is SessionMode.CORTEX:
            reply = self.think(message, context=ctx).amalgam.text
        else:
            reply = self._responder(message, session.turns, ctx)
        session.add_turn("jeeves", reply)
        self._bus.emit("jeeves.turn.completed",
                       {"session_id": session_id, "turns": len(session.turns)})
        return reply

    def review_code(self, session_id: str, code: str) -> dict[str, Any]:
        """Co-coding mode: lightweight static review of learner code."""
        session = self._get(session_id)
        if session.mode is not SessionMode.CO_CODING:
            raise SessionError("review_code requires co_coding mode",
                               context={"session_id": session_id})
        findings: list[dict[str, Any]] = []
        for i, line in enumerate(code.splitlines(), start=1):
            if "eval(" in line or "exec(" in line:
                findings.append({"line": i, "severity": "error",
                                 "message": "avoid eval/exec — unsafe dynamic execution"})
            elif len(line) > 120:
                findings.append({"line": i, "severity": "style",
                                 "message": "line over 120 characters"})
        summary = "Looks clean." if not findings else f"{len(findings)} finding(s)."
        self._bus.emit("jeeves.review.completed",
                       {"session_id": session_id, "findings": len(findings)})
        return {"findings": findings, "summary": summary}

    def get_session(self, session_id: str) -> Session:
        return self._get(session_id)

    def _brain_get(self):
        if self._brain is None:
            from skeleton.jeeves.tactical import TacticalBrain
            self._brain = TacticalBrain(self.era)
        return self._brain

    @property
    def cortex(self):
        if self._cortex is None:
            from skeleton.cortex import JeevesCortex
            self._cortex = JeevesCortex(bus=self._bus)
        return self._cortex

    @cortex.setter
    def cortex(self, value) -> None:
        self._cortex = value

    def think(self, stimulus: str, *, context: dict[str, Any] | None = None):
        """Neocortex think — the model in training, not a chat wrapper."""
        trace = self.cortex.think(stimulus, context)
        self._bus.emit("jeeves.cortex.thought", {
            "fp": trace.fingerprint, "used_own": trace.used_own,
            "hive": trace.hive_value,
        })
        return trace

    def bind_model(self, slot: str, backend=None, *, echo: bool = False, local: bool = False):
        if echo:
            return self.cortex.bind_echo(slot)
        if local or backend is None:
            return self.cortex.bind_local(slot)
        return self.cortex.bind(slot, backend)

    def acquire(self, slot: str) -> dict[str, Any]:
        out = self.cortex.acquire(slot)
        self._bus.emit("jeeves.cortex.acquired", out)
        return out

    def surpass(self, slot: str) -> dict[str, Any]:
        out = self.cortex.surpass(slot)
        self._bus.emit("jeeves.cortex.surpass", out)
        return out

    def bind_pack(self, pack: dict[str, Any]) -> dict[str, Any]:
        self.era = str(pack.get("era") or self.era)
        pack = self._brain_get().bind_pack(pack)
        self._bus.emit("jeeves.era.bound", {"era": pack["era"], "dps": pack["primary_dps"]})
        return pack

    def bind_era(self, era: str) -> dict[str, Any]:
        from skeleton.forge.eras import compile_era
        return self.bind_pack(compile_era(era))

    def plan_build(self, pack: dict[str, Any] | None = None, *,
                   tensor=None, reading=None) -> dict[str, Any]:
        """Jeeves-as-builder: design the run the forge will emit."""
        from skeleton.jeeves.builder import BuilderBrain
        if pack is None:
            from skeleton.forge.eras import compile_era
            pack = compile_era(self.era)
        plan = BuilderBrain().plan(pack, tensor=tensor, reading=reading)
        self.last_plan = plan
        self._bus.emit("jeeves.build.planned", {
            "era": plan.era, "seed": plan.seed, "bias": plan.room_bias,
        })
        return plan.to_dict()

    def advise(self, session_id: str, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
        """Tactical cascade. Opens nothing; uses bound era + live telemetry."""
        session = self._get(session_id)
        brain = self._brain_get()
        advice = brain.advise(telemetry or {})
        top = advice[0]
        session.add_turn("jeeves", top.text)
        self._bus.emit("jeeves.advice.issued",
                       {"session_id": session_id, "priority": top.priority, "axis": top.axis})
        return {
            "era": brain.era,
            "world": brain.observe(telemetry or {}).to_dict(),
            "advice": [a.to_dict() for a in advice],
            "next": top.to_dict(),
        }

    def _get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionError("unknown session", context={"session_id": session_id})
        return session
