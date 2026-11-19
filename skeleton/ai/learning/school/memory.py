"""Bounded provider-neutral learner memory and deterministic retrieval."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite, log1p
from typing import Iterable, Sequence

MAX_MEMORIES = 4096
MAX_MEMORY_BYTES = 16 << 20
MAX_TEXT = 16_384
MAX_TERMS = 128
MAX_LIMIT = 256


class MemoryKind(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    MISCONCEPTION = "misconception"
    PREFERENCE = "preference"
    GOAL = "goal"


def _text(value, maximum):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError("invalid memory text")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError("memory text exceeds byte budget")
    return value


def _terms(values, maximum=256):
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("bounded sequence required")
    if len(values) > MAX_TERMS:
        raise ValueError("too many memory terms")
    return tuple(_text(value, maximum) for value in values if value != "")


def _unit(value):
    if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
        raise ValueError("memory confidence and importance must be finite in [0,1]")


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
        _text(self.key, 256)
        _text(self.content, MAX_TEXT)
        if not isinstance(self.kind, MemoryKind):
            raise ValueError("canonical memory kind required")
        skills = _terms(self.skill_ids)
        if len(set(skills)) != len(skills):
            raise ValueError("duplicate memory skill")
        object.__setattr__(self, "skill_ids", skills)
        _unit(self.importance)
        _unit(self.confidence)
        if type(self.access_count) is not int or not 0 <= self.access_count < 1 << 63:
            raise ValueError("invalid memory access count")
        if (type(self.age_hours) not in (int, float) or not isfinite(self.age_hours)
                or not 0 <= self.age_hours <= 1e9):
            raise ValueError("invalid memory age")

    @property
    def retention_signal(self) -> float:
        recency = 1.0 / (1.0 + log1p(self.age_hours) / 4.0)
        frequency = min(1.0, log1p(self.access_count) / 3.0)
        return min(1.0, 0.45 * recency + 0.25 * frequency + 0.30 * self.importance)


@dataclass(frozen=True)
class MemoryMatch:
    memory: LearnerMemory
    score: float
    reason: str


def _size(memory):
    if not isinstance(memory, LearnerMemory):
        raise TypeError("canonical LearnerMemory required")
    return 128 + len(memory.key.encode()) + len(memory.content.encode()) + sum(
        len(skill.encode()) + 8 for skill in memory.skill_ids
    )


@dataclass
class MemoryStore:
    memories: list[LearnerMemory] = field(default_factory=list)

    def __post_init__(self):
        source = self.memories
        self.memories = []
        self.extend(source)

    def _checked(self):
        if type(self.memories) is not list or len(self.memories) > MAX_MEMORIES:
            raise ValueError("memory capacity exceeded")
        sizes = {}
        for item in self.memories:
            size = _size(item)
            if item.key in sizes:
                raise ValueError("duplicate stored memory identity")
            sizes[item.key] = size
        if sum(sizes.values()) > MAX_MEMORY_BYTES:
            raise ValueError("memory byte budget exceeded")
        return sizes

    def remember(self, memory: LearnerMemory) -> None:
        self.extend((memory,))

    def extend(self, memories: Iterable[LearnerMemory]) -> None:
        sizes = self._checked()
        total = sum(sizes.values())
        staged = {item.key: item for item in self.memories}
        for index, memory in enumerate(memories):
            if index >= MAX_MEMORIES:
                raise ValueError("memory batch budget exceeded")
            size = _size(memory)
            old = sizes.get(memory.key, 0)
            if old == 0 and len(staged) >= MAX_MEMORIES:
                raise ValueError("memory capacity exceeded")
            if total - old + size > MAX_MEMORY_BYTES:
                raise ValueError("memory byte budget exceeded")
            total += size - old
            sizes[memory.key] = size
            staged.pop(memory.key, None)
            staged[memory.key] = memory
        self.memories = list(staged.values())

    def retrieve(self, *, query_terms: Sequence[str] = (), skill_ids: Sequence[str] = (),
                 kinds: Sequence[MemoryKind] = (), limit: int = 5) -> list[MemoryMatch]:
        if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
            raise ValueError("invalid memory retrieval limit")
        self._checked()
        terms = {term.casefold() for term in _terms(query_terms) if term.strip()}
        skills = set(_terms(skill_ids))
        if not isinstance(kinds, Sequence) or len(kinds) > len(MemoryKind):
            raise ValueError("invalid memory kinds")
        if any(not isinstance(kind, MemoryKind) for kind in kinds):
            raise ValueError("invalid memory kind")
        allowed = set(kinds)
        matches = []
        for memory in self.memories:
            if allowed and memory.kind not in allowed:
                continue
            text = f"{memory.key} {memory.content}".casefold()
            lexical = sum(1 for term in terms if term in text) / max(1, len(terms))
            skill = len(skills.intersection(memory.skill_ids)) / max(1, len(skills))
            score = 0.40 * lexical + 0.30 * skill + 0.30 * memory.retention_signal
            if score > 0:
                reason = "lexical+skill+retention" if lexical and skill else "retention-supported match"
                matches.append(MemoryMatch(memory, score, reason))
        return sorted(matches, key=lambda match: (-match.score, match.memory.key))[:limit]

    def retention_due(self, *, minimum_signal: float = 0.55) -> list[LearnerMemory]:
        _unit(minimum_signal)
        self._checked()
        return [item for item in self.memories if item.retention_signal < minimum_signal]
