"""Quest fail states as an overlay on the Director stack.

The Director engine has stages, OR-solutions and per-solution
``outcome_flag`` branches, but no way for a quest to *fail* (no abandon,
timeout or lost-escort state).  This module adds only that, evaluated
read-only from a :class:`DirectorState` and optional escort replays.  The
engine itself is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from skeleton.ai.game_builder.quest_encounter_runtime import (
    EncounterReplay, EncounterSpec, encounter_verify,
)
from skeleton.ai.game_builder.quest_scene_engine import DirectorState

FAIL_KINDS = frozenset({"turn_limit", "flag", "escort_lost"})


@dataclass(frozen=True, slots=True)
class FailCondition:
    """``turn_limit``: quest not complete once ``turn > limit``.
    ``flag``: a narrative flag was set (e.g. a rival branch's outcome).
    ``escort_lost``: the verified escort encounter ended ``"lost"``."""

    quest: str
    kind: str
    limit: int = 0
    flag: str = ""
    encounter: EncounterSpec | None = None

    def __post_init__(self) -> None:
        if self.kind not in FAIL_KINDS:
            raise ValueError(f"unknown fail kind {self.kind!r}")
        if self.kind == "turn_limit" and self.limit < 1:
            raise ValueError("turn_limit needs a positive limit")
        if self.kind == "flag" and not self.flag:
            raise ValueError("flag condition needs a flag")
        if self.kind == "escort_lost" and self.encounter is None:
            raise ValueError("escort_lost needs an encounter")


@dataclass(frozen=True, slots=True)
class QuestFailure:
    quest: str
    kind: str
    reason: str


def evaluate_failures(state: DirectorState, conditions: Sequence[FailCondition], *,
                      escorts: Mapping[str, EncounterReplay] | None = None,
                      ) -> tuple[QuestFailure, ...]:
    """Failures for quests that are not already complete.

    ``escorts`` maps an encounter key to its replay; replays are verified.
    """
    escorts = escorts or {}
    failed: list[QuestFailure] = []
    for c in conditions:
        if c.quest in state.complete:
            continue
        if c.kind == "turn_limit" and state.turn > c.limit:
            failed.append(QuestFailure(c.quest, c.kind, f"turn {state.turn} > {c.limit}"))
        elif c.kind == "flag" and c.flag in state.narrative_flags:
            failed.append(QuestFailure(c.quest, c.kind, f"flag {c.flag} set"))
        elif c.kind == "escort_lost":
            replay = escorts.get(c.encounter.key)
            if replay is not None:
                encounter_verify(c.encounter, replay)
                if replay.final.status == "lost":
                    failed.append(QuestFailure(c.quest, c.kind, "escort encounter lost"))
    return tuple(failed)


def failed_quests(failures: Sequence[QuestFailure]) -> frozenset[str]:
    return frozenset(f.quest for f in failures)


__all__ = ["FAIL_KINDS", "FailCondition", "QuestFailure", "evaluate_failures", "failed_quests"]
