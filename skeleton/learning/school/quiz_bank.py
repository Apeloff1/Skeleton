"""Offline progressive-difficulty quiz bank for Jeeves.

Ported from the Tutolage sibling repo (``backend/routes/quiz_bank.py``),
which kept 285 questions in Mongo behind FastAPI routes.  This port keeps
the useful pattern -- a typed bank with five difficulty tiers, a fixed
per-quiz tier mix and deterministic grading -- without network, database
or randomness that cannot be replayed.  Selection is seeded so the same
learner/seed pair always gets the same quiz.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "DIFFICULTY_NAMES",
    "QuizBankError",
    "QuizQuestion",
    "QuizBank",
    "QuizResult",
    "TIER_MIX",
    "default_bank",
]

DIFFICULTY_NAMES: Mapping[int, str] = {1: "easy", 2: "medium", 3: "hard", 4: "expert", 5: "mastery"}
# Tutolage distribution per 95-question subject: 20/25/25/15/10.
TIER_MIX: Mapping[int, float] = {1: 20 / 95, 2: 25 / 95, 3: 25 / 95, 4: 15 / 95, 5: 10 / 95}
MAX_QUIZ = 100


class QuizBankError(ValueError):
    """Raised for malformed questions or impossible quiz requests."""


@dataclass(frozen=True)
class QuizQuestion:
    subject: str
    category: str
    prompt: str
    options: Tuple[str, ...]
    answer: str
    explanation: str
    difficulty: int

    def __post_init__(self) -> None:
        if self.difficulty not in DIFFICULTY_NAMES:
            raise QuizBankError(f"difficulty out of range: {self.difficulty}")
        if len(self.options) < 2:
            raise QuizBankError("need at least two options")
        if len(set(self.options)) != len(self.options):
            raise QuizBankError("duplicate options")
        if self.answer not in self.options:
            raise QuizBankError("answer must be one of the options")
        if not self.prompt.strip() or not self.subject.strip():
            raise QuizBankError("prompt and subject are required")

    @property
    def qid(self) -> str:
        raw = f"{self.subject}|{self.category}|{self.prompt}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True)
class QuizResult:
    total: int
    correct: int
    by_difficulty: Mapping[int, Tuple[int, int]]
    feedback: Tuple[Tuple[str, bool, str], ...]

    @property
    def score(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def mastery_tier(self) -> int:
        """Highest tier where every asked question at or below it was right."""
        tier = 0
        for level in sorted(DIFFICULTY_NAMES):
            asked, right = self.by_difficulty.get(level, (0, 0))
            if asked and right < asked:
                break
            if asked:
                tier = level
        return tier


@dataclass
class QuizBank:
    questions: List[QuizQuestion] = field(default_factory=list)

    def add(self, question: QuizQuestion) -> None:
        if any(q.qid == question.qid for q in self.questions):
            raise QuizBankError(f"duplicate question {question.qid}")
        self.questions.append(question)

    def extend(self, questions: Iterable[QuizQuestion]) -> None:
        for q in questions:
            self.add(q)

    def subjects(self) -> List[str]:
        return sorted({q.subject for q in self.questions})

    def filter(self, subject: Optional[str] = None, difficulty: Optional[int] = None,
               category: Optional[str] = None) -> List[QuizQuestion]:
        return [q for q in self.questions
                if (subject is None or q.subject == subject)
                and (difficulty is None or q.difficulty == difficulty)
                and (category is None or q.category == category)]

    def stats(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for q in self.questions:
            row = out.setdefault(q.subject, {name: 0 for name in DIFFICULTY_NAMES.values()})
            row[DIFFICULTY_NAMES[q.difficulty]] += 1
        return out

    def build_quiz(self, subject: str, size: int, *, seed: str = "",
                   max_difficulty: int = 5) -> List[QuizQuestion]:
        """Pick ``size`` questions following TIER_MIX, easiest first.

        Tiers above ``max_difficulty`` are excluded; shortfalls in one tier
        are back-filled from neighbouring allowed tiers.
        """
        if not 1 <= size <= MAX_QUIZ:
            raise QuizBankError(f"size must be 1..{MAX_QUIZ}")
        if max_difficulty not in DIFFICULTY_NAMES:
            raise QuizBankError("max_difficulty out of range")
        pool = {d: sorted(self.filter(subject, d), key=lambda q: q.qid)
                for d in DIFFICULTY_NAMES if d <= max_difficulty}
        available = sum(len(v) for v in pool.values())
        if available < size:
            raise QuizBankError(f"only {available} questions for {subject!r}")
        rng = random.Random(hashlib.sha256(f"{subject}|{seed}".encode()).hexdigest())
        for qs in pool.values():
            rng.shuffle(qs)
        weight = sum(TIER_MIX[d] for d in pool)
        want = {d: int(size * TIER_MIX[d] / weight) for d in pool}
        # distribute rounding remainder to the lowest tiers first
        level_cycle = sorted(pool)
        i = 0
        while sum(want.values()) < size:
            want[level_cycle[i % len(level_cycle)]] += 1
            i += 1
        picked: Dict[int, List[QuizQuestion]] = {d: pool[d][: want[d]] for d in pool}
        short = size - sum(len(v) for v in picked.values())
        for d in sorted(pool):
            if short <= 0:
                break
            spare = pool[d][len(picked[d]):]
            take = spare[:short]
            picked[d].extend(take)
            short -= len(take)
        return [q for d in sorted(picked) for q in picked[d]]

    @staticmethod
    def grade(quiz: Sequence[QuizQuestion], answers: Mapping[str, str]) -> QuizResult:
        by: Dict[int, List[int]] = {}
        feedback = []
        correct = 0
        for q in quiz:
            ok = answers.get(q.qid) == q.answer
            correct += ok
            row = by.setdefault(q.difficulty, [0, 0])
            row[0] += 1
            row[1] += ok
            feedback.append((q.qid, ok, q.explanation))
        return QuizResult(len(quiz), correct, {k: (v[0], v[1]) for k, v in by.items()}, tuple(feedback))


_SEED: Tuple[Tuple[str, str, str, Tuple[str, ...], str, str, int], ...] = (
    ("physics", "mechanics", "What is Newton's First Law also known as?",
     ("Law of Inertia", "Law of Acceleration", "Law of Reaction", "Law of Gravity"), "Law of Inertia",
     "An object keeps its state of motion unless an external force acts on it.", 1),
    ("physics", "mechanics", "Kinetic energy formula is KE = ?", ("mv", "½mv²", "mgh", "½mv"), "½mv²",
     "Kinetic energy is half the mass times velocity squared.", 1),
    ("physics", "game_physics", "Why use fixed timestep physics?",
     ("Faster rendering", "Deterministic results", "Less memory", "Better graphics"), "Deterministic results",
     "A fixed step keeps the simulation consistent regardless of frame rate.", 2),
    ("physics", "game_physics", "Broad phase collision detection uses?",
     ("AABBs and spatial hashing", "Exact geometry", "Pixel-perfect checks", "Ray marching"),
     "AABBs and spatial hashing", "Broad phase cheaply discards pairs that cannot collide.", 3),
    ("physics", "game_physics", "GJK algorithm is used for?",
     ("Convex collision detection", "Pathfinding", "Rendering", "Audio"), "Convex collision detection",
     "Gilbert-Johnson-Keerthi tests intersection between convex shapes.", 4),
    ("physics", "game_physics", "Sequential Impulse is used for?",
     ("Constraint solving", "Rendering", "Audio mixing", "Networking"), "Constraint solving",
     "It iteratively applies corrective impulses until constraints hold.", 5),
    ("math", "linear_algebra", "The dot product of perpendicular vectors is?", ("0", "1", "-1", "undefined"),
     "0", "cos(90°) is zero.", 1),
    ("math", "interpolation", "Lerp(a, b, 0.5) returns?", ("a", "b", "the midpoint", "a*b"), "the midpoint",
     "Linear interpolation at t=0.5 is halfway between a and b.", 2),
    ("math", "rotation", "Quaternions avoid which rotation problem?",
     ("Gimbal lock", "Aliasing", "Z-fighting", "Overdraw"), "Gimbal lock",
     "They represent orientation without the degenerate Euler-angle axis alignment.", 3),
    ("cs", "data_structures", "Average lookup cost in a hash table is?", ("O(1)", "O(log n)", "O(n)", "O(n²)"),
     "O(1)", "Hashing maps keys directly to buckets.", 1),
    ("cs", "algorithms", "A* is optimal when its heuristic is?",
     ("Admissible", "Random", "Negative", "Exponential"), "Admissible",
     "A heuristic that never overestimates guarantees an optimal path.", 3),
    ("cs", "networking", "Client-side prediction mainly hides?",
     ("Latency", "Packet size", "Encryption cost", "Disk I/O"), "Latency",
     "The client simulates locally and reconciles with the authoritative server.", 4),
)


def default_bank() -> QuizBank:
    """A small curated seed bank (subset of the Tutolage source)."""
    bank = QuizBank()
    bank.extend(QuizQuestion(s, c, p, o, a, e, d) for s, c, p, o, a, e, d in _SEED)
    return bank
