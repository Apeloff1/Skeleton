"""B036 — Dialogue/voice orchestration.

Success criterion (game_creation_batches.json): "Dialogue uses context,
persona, safety and latency budgets with recoverable fallback."

* :func:`build_context` grounds a turn in B034 percepts and B035 canon facts —
  generators see only what the speaking NPC perceives plus canon about those
  entities, never raw world state.
* :class:`Persona` constrains style (max length, banned topics, voice id).
* :class:`SafetyPolicy` blocks unsafe text and canon contradictions (a line
  must not mention an entity the canon marks dead as present).
* :class:`DialogueOrchestrator` tries each :class:`Generator` in order under a
  per-turn latency budget measured on an injected clock. A generator that
  raises, overruns its slice, or produces rejected text is skipped and the
  next one tried; if all fail the persona's authored fallback line is used, so
  a turn always produces a recoverable, safe utterance with a full trace.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

SCHEMA = "gameforge.b036.dialogue.v1"


class DialogueError(ValueError):
    pass


@dataclass(frozen=True)
class Persona:
    npc_id: str
    voice_id: str
    max_chars: int = 240
    banned_topics: tuple[str, ...] = ()
    fallback_line: str = "..."

    def __post_init__(self) -> None:
        if not self.npc_id or not self.voice_id:
            raise DialogueError("persona needs npc_id and voice_id")
        if not 8 <= self.max_chars <= 4000:
            raise DialogueError("max_chars out of range")
        if not self.fallback_line or len(self.fallback_line) > self.max_chars:
            raise DialogueError("fallback_line must fit the persona")


@dataclass(frozen=True)
class DialogueContext:
    npc_id: str
    player_line: str
    visible: tuple[str, ...]
    canon: Mapping[tuple[str, str], str]
    history: tuple[str, ...] = ()


def build_context(npc_id: str, player_line: str, percepts: Iterable, canon=None,
                  history: Iterable[str] = (), *, max_history: int = 8) -> DialogueContext:
    visible = tuple(p.entity_id for p in percepts)
    facts: dict[tuple[str, str], str] = {}
    if canon is not None:
        for (ent, attr), v in canon.facts.items():
            if ent in visible or ent == npc_id:
                facts[(ent, attr)] = v
    return DialogueContext(npc_id, player_line[:1000], visible, facts, tuple(history)[-max_history:])


@dataclass(frozen=True)
class SafetyPolicy:
    blocked_patterns: tuple[str, ...] = (r"(?i)\bkill yourself\b", r"(?i)\b(password|api[_ -]?key)\b")
    dead_entities: frozenset[str] = frozenset()

    def check(self, text: str, persona: Persona, ctx: DialogueContext) -> str | None:
        if not isinstance(text, str) or not text.strip():
            return "empty"
        if len(text) > persona.max_chars:
            return "too_long"
        for pat in self.blocked_patterns:
            if re.search(pat, text):
                return "unsafe"
        low = text.lower()
        for t in persona.banned_topics:
            if t.lower() in low:
                return "banned_topic"
        dead = set(self.dead_entities) | {e for (e, a), v in ctx.canon.items() if a == "status" and v == "dead"}
        for e in dead:
            if re.search(rf"(?i)\b{re.escape(e)}\b (is here|is with us|stands)", text):
                return "canon_contradiction"
        return None


@dataclass(frozen=True)
class Generator:
    name: str
    fn: Callable[[DialogueContext, Persona], str]
    cost: float = 0.0


@dataclass(frozen=True)
class Utterance:
    npc_id: str
    voice_id: str
    text: str
    source: str
    trace: tuple[tuple[str, str], ...]
    elapsed_ms: float
    cost: float


@dataclass
class DialogueOrchestrator:
    generators: tuple[Generator, ...]
    safety: SafetyPolicy = field(default_factory=SafetyPolicy)
    budget_ms: float = 800.0
    clock: Callable[[], float] = None  # seconds; injected for determinism

    def __post_init__(self) -> None:
        if self.clock is None:
            import time
            self.clock = time.monotonic
        if self.budget_ms <= 0:
            raise DialogueError("budget_ms must be positive")
        names = [g.name for g in self.generators]
        if len(set(names)) != len(names):
            raise DialogueError("generator names must be unique")

    def respond(self, ctx: DialogueContext, persona: Persona) -> Utterance:
        if ctx.npc_id != persona.npc_id:
            raise DialogueError("context and persona disagree on npc")
        start = self.clock()
        trace: list[tuple[str, str]] = []
        cost = 0.0
        for g in self.generators:
            spent = (self.clock() - start) * 1000
            if spent >= self.budget_ms:
                trace.append((g.name, "skipped_budget"))
                continue
            t0 = self.clock()
            try:
                text = g.fn(ctx, persona)
            except Exception as exc:
                trace.append((g.name, f"error:{type(exc).__name__}"))
                cost += g.cost
                continue
            cost += g.cost
            took = (self.clock() - t0) * 1000
            if (self.clock() - start) * 1000 > self.budget_ms:
                trace.append((g.name, f"over_budget:{took:.0f}ms"))
                continue
            verdict = self.safety.check(text, persona, ctx)
            if verdict:
                trace.append((g.name, f"rejected:{verdict}"))
                continue
            trace.append((g.name, "ok"))
            return Utterance(persona.npc_id, persona.voice_id, text.strip(), g.name, tuple(trace),
                             (self.clock() - start) * 1000, cost)
        trace.append(("fallback", "ok"))
        return Utterance(persona.npc_id, persona.voice_id, persona.fallback_line, "fallback", tuple(trace),
                         (self.clock() - start) * 1000, cost)
