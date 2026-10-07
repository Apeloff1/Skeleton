"""Deterministic learning-state primitives promoted from tutoring systems.

The kernel owns state transitions; provider-specific tutoring logic stays at
an adapter boundary. This makes progress reproducible and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Mastery(IntEnum):
    NOVICE = 0
    DEVELOPING = 1
    PROFICIENT = 2
    MASTERED = 3


@dataclass(frozen=True, slots=True)
class LearningState:
    learner: str
    subject: str
    mastery: Mastery = Mastery.NOVICE
    attempts: int = 0
    successes: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    def record(self, success: bool) -> LearningState:
        attempts = self.attempts + 1
        successes = self.successes + int(success)
        mastery = self.mastery
        if success and successes >= 3:
            mastery = Mastery(min(int(Mastery.MASTERED), int(mastery) + 1))
        elif not success and attempts >= 3 and self.success_rate < 0.5:
            mastery = Mastery(max(int(Mastery.NOVICE), int(mastery) - 1))
        return LearningState(self.learner, self.subject, mastery, attempts, successes)


def assess(state: LearningState, *, successes: int, attempts: int) -> LearningState:
    """Apply a bounded assessment result to an existing learner state."""
    if attempts < 0 or successes < 0 or successes > attempts:
        raise ValueError("assessment counts must satisfy 0 <= successes <= attempts")
    current = state
    for index in range(attempts):
        current = current.record(index < successes)
    return current
