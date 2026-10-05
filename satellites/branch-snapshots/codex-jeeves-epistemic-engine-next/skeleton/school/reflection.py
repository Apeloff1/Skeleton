"""Provider-neutral reflection and learner journal policies mined from Newfix.

The source Captain's Log mixes persistence/UI concerns with a useful pedagogical
idea: automatically capture discoveries, failures, milestones, relationships,
quests and lessons learned, then make those moments retrievable.  This module
keeps only that decision layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class ReflectionKind(str, Enum):
    DISCOVERY = "discovery"
    SUCCESS = "success"
    FAILURE = "failure"
    MILESTONE = "milestone"
    MISCONCEPTION = "misconception"
    RELATIONSHIP = "relationship"
    CHALLENGE = "challenge"
    INSIGHT = "insight"
    GOAL = "goal"


class ReflectionImportance(str, Enum):
    NORMAL = "normal"
    KNOWLEDGE = "knowledge"
    MILESTONE = "milestone"
    ACHIEVEMENT = "achievement"
    LEGENDARY = "legendary"


@dataclass(frozen=True)
class ReflectionEntry:
    """An episodic learning event suitable for memory storage."""

    entry_id: str
    kind: ReflectionKind
    title: str
    content: str
    importance: ReflectionImportance = ReflectionImportance.NORMAL
    skills: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    lesson_learned: str | None = None
    pinned: bool = False


@dataclass(frozen=True)
class ReflectionPrompt:
    """A prompt that turns an event into metacognitive evidence."""

    question: str
    purpose: str
    required: bool = False


REFLECTION_PROMPTS: Mapping[ReflectionKind, tuple[ReflectionPrompt, ...]] = {
    ReflectionKind.SUCCESS: (
        ReflectionPrompt("What did you do that made this work?", "identify successful strategy"),
        ReflectionPrompt("What would you repeat next time?", "extract reusable procedure"),
    ),
    ReflectionKind.FAILURE: (
        ReflectionPrompt("What changed when your approach failed?", "diagnose causal evidence", True),
        ReflectionPrompt("What is the smallest experiment you could try next?", "convert failure into experiment"),
    ),
    ReflectionKind.MISCONCEPTION: (
        ReflectionPrompt("What did you believe before, and what evidence changed it?", "repair the mental model", True),
    ),
    ReflectionKind.MILESTONE: (
        ReflectionPrompt("What can you do now that you could not do before?", "make growth explicit", True),
    ),
    ReflectionKind.DISCOVERY: (
        ReflectionPrompt("Why is this discovery useful?", "connect knowledge to application"),
    ),
    ReflectionKind.CHALLENGE: (
        ReflectionPrompt("Which part was hardest, and why?", "locate productive difficulty"),
    ),
    ReflectionKind.RELATIONSHIP: (
        ReflectionPrompt("What did this interaction teach you?", "extract social/contextual learning"),
    ),
    ReflectionKind.INSIGHT: (
        ReflectionPrompt("How does this connect to something you already know?", "build transfer links"),
    ),
    ReflectionKind.GOAL: (
        ReflectionPrompt("What evidence would show that this goal is getting closer?", "make goals measurable"),
    ),
}


@dataclass
class ReflectionJournal:
    """In-memory journal policy; persistence is deliberately adapter-owned."""

    entries: list[ReflectionEntry] = field(default_factory=list)

    def record(self, entry: ReflectionEntry) -> None:
        if not entry.entry_id:
            raise ValueError("entry_id must not be empty")
        if not entry.title.strip() or not entry.content.strip():
            raise ValueError("reflection title and content are required")
        self.entries.append(entry)

    def recent(self, limit: int = 10) -> list[ReflectionEntry]:
        if limit < 1:
            raise ValueError("limit must be positive")
        return list(reversed(self.entries[-limit:]))

    def milestones(self) -> list[ReflectionEntry]:
        return [
            entry
            for entry in self.entries
            if entry.importance in {
                ReflectionImportance.MILESTONE,
                ReflectionImportance.ACHIEVEMENT,
                ReflectionImportance.LEGENDARY,
            }
        ]

    def for_skill(self, skill: str) -> list[ReflectionEntry]:
        return [entry for entry in reversed(self.entries) if skill in entry.skills]

    def lessons(self) -> list[str]:
        return [entry.lesson_learned for entry in self.entries if entry.lesson_learned]


def reflection_prompts(kind: ReflectionKind) -> tuple[ReflectionPrompt, ...]:
    return REFLECTION_PROMPTS[kind]


def summarize_reflection(entries: Iterable[ReflectionEntry]) -> dict[str, object]:
    """Produce compact evidence for a tutor without generating prose."""
    items = list(entries)
    skills = sorted({skill for entry in items for skill in entry.skills})
    return {
        "events": len(items),
        "skills": skills,
        "failures": sum(entry.kind == ReflectionKind.FAILURE for entry in items),
        "misconceptions": sum(entry.kind == ReflectionKind.MISCONCEPTION for entry in items),
        "milestones": sum(entry.importance in {ReflectionImportance.MILESTONE, ReflectionImportance.ACHIEVEMENT, ReflectionImportance.LEGENDARY} for entry in items),
        "lessons": [entry.lesson_learned for entry in items if entry.lesson_learned],
    }
