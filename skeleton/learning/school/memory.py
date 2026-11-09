"""Provider-agnostic learner memory for Jeeves.

Mined from the Jeeves Core design in Interesting-22: long-term tutor memory,
retrieval by relevance, and memory-aware teaching.  This deliberately avoids
ChromaDB, embeddings, HTTP, or model-provider dependencies; adapters can plug
those in above this deterministic policy layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import log1p
from typing import Iterable, Sequence


class MemoryKind(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    MISCONCEPTION = "misconception"
    PREFERENCE = "preference"
    GOAL = "goal"


@dataclass(frozen=True)
class LearnerMemory:
    key: str
    content: str
    kind: MemoryKind
    skill_ids: tuple[str, ...] = ()
    importance: float = 0.5
    confidence: float = 0.5
    access_count: int = 0
    age_hours: float = 0.0

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.content.strip():
            raise ValueError("memory key and content must be non-empty")
        if not 0 <= self.importance <= 1 or not 0 <= self.confidence <= 1:
            raise ValueError("importance and confidence must be between 0 and 1")
        if self.access_count < 0 or self.age_hours < 0:
            raise ValueError("access_count and age_hours must be non-negative")

    @property
    def retention_signal(self) -> float:
        # Recency decays slowly; repeated access and importance stabilize recall.
        recency = 1.0 / (1.0 + log1p(self.age_hours) / 4.0)
        frequency = min(1.0, log1p(self.access_count) / 3.0)
        return min(1.0, 0.45 * recency + 0.25 * frequency + 0.30 * self.importance)


@dataclass(frozen=True)
class MemoryMatch:
    memory: LearnerMemory
    score: float
    reason: str


@dataclass
class MemoryStore:
    memories: list[LearnerMemory] = field(default_factory=list)

    def remember(self, memory: LearnerMemory) -> None:
        self.memories = [item for item in self.memories if item.key != memory.key]
        self.memories.append(memory)

    def extend(self, memories: Iterable[LearnerMemory]) -> None:
        for memory in memories:
            self.remember(memory)

    def retrieve(
        self,
        *,
        query_terms: Sequence[str] = (),
        skill_ids: Sequence[str] = (),
        kinds: Sequence[MemoryKind] = (),
        limit: int = 5,
    ) -> list[MemoryMatch]:
        if limit < 1:
            raise ValueError("limit must be positive")
        terms = {term.lower() for term in query_terms if term.strip()}
        skills = set(skill_ids)
        allowed_kinds = set(kinds)
        matches: list[MemoryMatch] = []
        for memory in self.memories:
            if allowed_kinds and memory.kind not in allowed_kinds:
                continue
            text = f"{memory.key} {memory.content}".lower()
            lexical = sum(1 for term in terms if term in text) / max(1, len(terms))
            skill = len(skills.intersection(memory.skill_ids)) / max(1, len(skills))
            score = 0.40 * lexical + 0.30 * skill + 0.30 * memory.retention_signal
            if score > 0:
                reason = "lexical+skill+retention" if lexical and skill else "retention-supported match"
                matches.append(MemoryMatch(memory, score, reason))
        return sorted(matches, key=lambda match: match.score, reverse=True)[:limit]

    def retention_due(self, *, minimum_signal: float = 0.55) -> list[LearnerMemory]:
        if not 0 <= minimum_signal <= 1:
            raise ValueError("minimum_signal must be between 0 and 1")
        return [m for m in self.memories if m.retention_signal < minimum_signal]
