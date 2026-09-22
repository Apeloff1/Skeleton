"""Jeeves pedagogy — scaffolded hints at degrading levels of support.

Tutoring is not dumping answers: the tutor escalates support, offering
hints (conceptual, structural, worked example) before revealing an answer.
This tracks the scaffold at each step so assessment sees what support
was needed.

- :class:`HintLevel` — how much help was given
- :class:`Scaffold` — tracks hints per interaction
- :class:`PedagogyEngine` — pick next hint level from state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from skeleton.kernel.errors import KernelError


class PedagogyError(KernelError):
    code = "JEE.PEDAGOGY"


class HintLevel(str, Enum):
    NONE = "NONE"
    CONCEPT = "CONCEPT"  # what to think about
    STRUCTURE = "STRUCTURE"  # how to organise
    EXAMPLE = "EXAMPLE"  # worked example
    ANSWER = "ANSWER"  # direct response


@dataclass(frozen=True)
class Hint:
    level: HintLevel
    text: str


@dataclass
class Scaffold:
    interaction_id: str
    used: List[Hint] = field(default_factory=list)

    def record(self, hint: Hint) -> None:
        self.used.append(hint)

    @property
    def current_level(self) -> HintLevel:
        return self.used[-1].level if self.used else HintLevel.NONE


class PedagogyEngine:
    """Escalates hints based on scaffold state."""

    ESCALATION = [
        HintLevel.CONCEPT,
        HintLevel.STRUCTURE,
        HintLevel.EXAMPLE,
        HintLevel.ANSWER,
    ]

    def next_hint(self, scaffold: Scaffold) -> HintLevel:
        if not scaffold.used:
            return self.ESCALATION[0]
        current = scaffold.current_level
        try:
            idx = self.ESCALATION.index(current)
            if idx < len(self.ESCALATION) - 1:
                return self.ESCALATION[idx + 1]
        except ValueError:
            pass
        return current

    def should_escalate(self, scaffold: Scaffold, level: HintLevel) -> bool:
        return scaffold.current_level in (
            HintLevel.NONE,
            level,
        )
