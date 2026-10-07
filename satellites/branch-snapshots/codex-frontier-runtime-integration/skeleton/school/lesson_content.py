"""Deterministic lesson-content generation mined from Interesting-22.

The source's class-week generator guarantees that a curriculum week resolves
into substantive material instead of a thin catalog entry.  Skeleton keeps
that idea as a provider-free content contract: stable topic explanations,
worked-code sketches, graduated exercises, objectives and a rubric.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
from typing import Sequence


@dataclass(frozen=True)
class LessonTopic:
    title: str
    explanation: str
    code_example: str | None = None


@dataclass(frozen=True)
class LessonExercise:
    prompt: str
    level: int


@dataclass(frozen=True)
class LessonContent:
    lesson_id: str
    week: int
    title: str
    category: str
    topics: tuple[LessonTopic, ...]
    exercises: tuple[LessonExercise, ...]
    learning_objectives: tuple[str, ...]
    assessment_rubric: tuple[str, ...]


_CATEGORY_KEYWORDS = {
    "algorithms": ("array", "tree", "graph", "sort", "search", "algorithm", "complexity"),
    "databases": ("sql", "table", "index", "query", "transaction", "schema", "database"),
    "networks": ("tcp", "udp", "http", "dns", "socket", "network", "routing"),
    "operating_systems": ("process", "thread", "scheduler", "memory", "kernel", "filesystem"),
    "compilers": ("lexer", "parser", "ast", "compiler", "ir", "codegen", "optimization"),
    "gamedev": ("game", "render", "shader", "physics", "collision", "animation", "ecs"),
    "oop": ("class", "object", "inheritance", "polymorphism", "encapsulation", "design pattern"),
}

_EXERCISES = (
    "Restate the concept in your own words, then identify one assumption the explanation makes.",
    "Implement the worked example from scratch and add one meaningful edge case.",
    "Design a failing test that would catch a likely regression in this topic.",
    "Find a real system using the technique and explain one trade-off its authors made.",
    "Compare this approach with an alternative and state when you would choose each.",
    "Teach the concept in five minutes without notes; record the question you could not answer.",
)


def _category(lesson_id: str, title: str, topics: Sequence[str]) -> str:
    haystack = " ".join((lesson_id, title, *topics)).lower()
    scores = {name: sum(word in haystack for word in words) for name, words in _CATEGORY_KEYWORDS.items()}
    return max(scores, key=scores.get) if max(scores.values()) else "computer_science"


def _rng(lesson_id: str, week: int) -> random.Random:
    digest = hashlib.sha256(f"{lesson_id}|{week}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _explanation(title: str, parent_title: str, rng: random.Random) -> str:
    frames = (
        "{topic} is a load-bearing part of {parent}. Start with the invariant, then study the operations that preserve it. The production question is not only whether the technique works, but what happens under failure, scale, contention, and maintenance.",
        "Treat {topic} as connective tissue in {parent}. The mechanics are usually compact; the difficult part is recognising the constraints under which they remain valid and noticing when a different approach becomes cheaper or clearer.",
        "The useful way to learn {topic} is to move from definition to worked example to failure mode. A solution that cannot survive an edge case is memorised syntax, not durable understanding.",
    )
    return rng.choice(frames).format(topic=title, parent=parent_title)


def _code_example(category: str, topic: str) -> str | None:
    if category == "algorithms":
        return f"# {topic}\ndef count_unique(values):\n    return len(set(values))"
    if category == "databases":
        return f"-- {topic}\nSELECT category, COUNT(*) AS total\nFROM items\nGROUP BY category\nORDER BY total DESC;"
    if category == "networks":
        return f"# {topic}\nimport socket\n\nwith socket.create_connection(('example.com', 80), timeout=5) as conn:\n    conn.sendall(b'GET / HTTP/1.1\\r\\nHost: example.com\\r\\n\\r\\n')"
    if category == "oop":
        return f"# {topic}\nclass Strategy:\n    def execute(self, value):\n        raise NotImplementedError"
    if category in {"gamedev", "operating_systems", "compilers"}:
        return f"# {topic}\n# Minimal sketch: isolate the invariant before adding framework code."
    return None


def generate_lesson_content(
    lesson_id: str,
    week: int,
    title: str,
    topics: Sequence[str],
) -> LessonContent:
    """Build stable, cacheable lesson content from a curriculum entry."""
    if not lesson_id.strip() or not title.strip() or week < 1:
        raise ValueError("lesson_id/title must be non-empty and week must be >= 1")
    if not topics:
        raise ValueError("at least one topic is required")
    rng = _rng(lesson_id, week)
    category = _category(lesson_id, title, topics)
    topic_objects = tuple(
        LessonTopic(topic, _explanation(topic, title, rng), _code_example(category, topic))
        for topic in topics
    )
    chosen = list(_EXERCISES)
    rng.shuffle(chosen)
    exercises = tuple(LessonExercise(prompt, level) for level, prompt in enumerate(chosen[:5], 1))
    objectives = tuple(f"Explain {topic} and identify its core invariant." for topic in topics)
    rubric = (
        "Recall: defines the concept and key vocabulary.",
        "Application: solves a representative problem independently.",
        "Analysis: identifies edge cases and trade-offs.",
        "Transfer: applies the idea in a new context and justifies the choice.",
    )
    return LessonContent(lesson_id, week, title, category, topic_objects, exercises, objectives, rubric)
