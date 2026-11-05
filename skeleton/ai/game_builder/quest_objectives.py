"""Typed quest objectives on top of the Director quest stack.

This module adds *no* new quest engine.  It gives designers five typed
objective kinds and maps each one onto what already exists:

* :mod:`quest_scene_engine` -- a typed objective becomes a Director
  :class:`Parameter`, several become a :class:`Solution` (an OR-branch of a
  :class:`QuestStage`).  The Director records progress per stage as
  ``(quest, stage, "kind:target", count)``; we only read those records.
* :mod:`skeleton.frontier.progression.quests` -- the same objectives render
  as frontier objective records and project Director records into
  :class:`ObjectiveProgress` / :class:`QuestProgressState`.
* :mod:`quest_encounter_runtime` -- an escort objective may carry an
  :class:`EncounterSpec`; it only completes when a verified encounter replay
  finished ``"won"``.

Branches already exist in the engine (several solutions per stage, each with
its own ``outcome_flag``), so nothing here re-implements them.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from skeleton.ai.game_builder.quest_encounter_runtime import (
    EncounterReplay, EncounterSpec, encounter_verify,
)
from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorState, Parameter, Solution,
)
from skeleton.frontier.progression.quests import ObjectiveProgress, QuestProgressState

ESCORT_ENCOUNTERS = frozenset({"escort_path", "escort_leash", "escort_introduction"})


class ObjectiveKind(str, Enum):
    KILL = "kill"
    COLLECT = "collect"
    REACH = "reach"
    TALK = "talk"
    ESCORT = "escort"

    @property
    def director_kind(self) -> str:
        return DIRECTOR_KIND[self]


#: Typed objective kind -> existing Director ``Parameter.kind`` (ACTION_TYPES).
DIRECTOR_KIND: Mapping[ObjectiveKind, str] = {
    ObjectiveKind.KILL: "fight",
    ObjectiveKind.COLLECT: "gather",
    ObjectiveKind.REACH: "travel",
    ObjectiveKind.TALK: "talk",
    ObjectiveKind.ESCORT: "escort_follow",
}


@dataclass(frozen=True, slots=True)
class TypedObjective:
    kind: ObjectiveKind
    target: str
    count: int = 1
    encounter: EncounterSpec | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ObjectiveKind(self.kind))
        if self.encounter is not None:
            if self.kind is not ObjectiveKind.ESCORT:
                raise ValueError("only escort objectives carry an encounter")
            if self.encounter.kind not in ESCORT_ENCOUNTERS:
                raise ValueError("escort objective needs an escort encounter")
        # Parameter enforces id shape and count bounds (1..100).
        self.to_parameter()

    @property
    def signature(self) -> str:
        return f"{self.kind.director_kind}:{self.target}"

    def to_parameter(self) -> Parameter:
        return Parameter(self.kind.director_kind, self.target, self.count)

    def to_spec_record(self) -> dict[str, object]:
        """Objective mapping accepted by frontier ``quest_from_record``."""
        return {"type": self.kind.value, "target": self.target, "count": self.count}


def to_solution(key: str, objectives: Sequence[TypedObjective], *,
                creativity: int = 0, outcome_flag: str = "path_original") -> Solution:
    """All ``objectives`` together form one OR-branch of a Director stage."""
    return Solution(key, tuple(o.to_parameter() for o in objectives),
                    creativity, outcome_flag)


def objectives_from_records(records: Sequence[Mapping[str, object]]) -> tuple[TypedObjective, ...]:
    """Parse frontier objective records (``type``/``target``/``count``)."""
    return tuple(TypedObjective(ObjectiveKind(str(r["type"])), str(r["target"]),
                                int(r.get("count", 1))) for r in records)


def _escort_won(objective: TypedObjective, replay: EncounterReplay | None) -> bool:
    if objective.encounter is None:
        return True
    if replay is None:
        return False
    encounter_verify(objective.encounter, replay)  # raises on a forged proof
    return replay.final.status == "won"


def objective_progress(state: DirectorState, quest: str, stage: str,
                       objectives: Sequence[TypedObjective], *,
                       escorts: Mapping[int, EncounterReplay] | None = None,
                       ) -> dict[str, ObjectiveProgress]:
    """Project Director records into frontier progress, keyed by index."""
    escorts = escorts or {}
    counts = {sig: n for q, st, sig, n in state.records if (q, st) == (quest, stage)}
    out: dict[str, ObjectiveProgress] = {}
    for i, obj in enumerate(objectives):
        current = min(obj.count, counts.get(obj.signature, 0))
        if current >= obj.count and not _escort_won(obj, escorts.get(i)):
            current = obj.count - 1
        out[str(i)] = ObjectiveProgress(current, obj.count, current >= obj.count)
    return out


def quest_progress(quest_id: str, progress: Mapping[str, ObjectiveProgress], *,
                   failed: bool = False) -> QuestProgressState:
    if failed:
        status = "failed"
    elif all(p.completed for p in progress.values()):
        status = "completed"
    else:
        status = "active"
    return QuestProgressState(quest_id, status, dict(progress))


__all__ = [
    "DIRECTOR_KIND", "ESCORT_ENCOUNTERS", "ObjectiveKind", "TypedObjective",
    "objective_progress", "objectives_from_records", "quest_progress", "to_solution",
]
