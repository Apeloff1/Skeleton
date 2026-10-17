"""Decompose a game brief into a swarm dependency graph.

The canonical plan is deterministic. An injected model may propose a graph,
and that proposal is used only when it matches the required gates. Anything
else falls back to the canonical plan so CI stays deterministic and a bad
model cannot drop QA or invent a cycle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from skeleton.automation.swarm.dag import SwarmDag
from skeleton.automation.swarm.studio.roles import StudioRole


class PlanError(ValueError):
    """The brief cannot be planned."""


class ModelClient(Protocol):
    def complete(self, *, role: str, prompt: str) -> Mapping[str, Any] | None:
        """Return a task graph, or None to keep the deterministic plan."""


GENRES = frozenset({"rpg", "arcade", "puzzle", "narrative", "platformer", "adventure"})
GENRE_ALIASES = {"platform": "platformer", "action": "arcade", "story": "narrative"}
CONSTRAINTS = frozenset({"omit-win-item", "small-cast", "no-combat"})


@dataclass(frozen=True)
class PlannedTask:
    id: str
    role: StudioRole
    capability: str
    deps: tuple[str, ...]
    goal: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "capability": self.capability,
            "deps": list(self.deps),
            "goal": self.goal,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PlannedTask":
        return cls(
            id=str(raw["id"]),
            role=StudioRole(str(raw["role"])),
            capability=str(raw["capability"]),
            deps=tuple(str(item) for item in raw.get("deps") or ()),
            goal=str(raw.get("goal") or ""),
        )


def normalize_brief(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise PlanError("brief must be an object")
    genre = str(raw.get("genre") or "adventure").strip().lower()
    genre = GENRE_ALIASES.get(genre, genre)
    if genre not in GENRES:
        genre = "adventure"
    title = _clean_line(raw.get("title")) or "Untitled Game"
    pitch = raw.get("pitch") if isinstance(raw.get("pitch"), str) else ""
    constraints: list[str] = []
    for item in raw.get("constraints") or ():
        if isinstance(item, str) and item in CONSTRAINTS and item not in constraints:
            constraints.append(item)
    must: list[str] = []
    for item in raw.get("must_include") or ():
        cleaned = _clean_line(item)
        if cleaned and cleaned.lower() not in {entry.lower() for entry in must}:
            must.append(cleaned[:40])
    return {
        "title": title[:80],
        "genre": genre,
        "pitch": pitch,
        "constraints": constraints,
        "must_include": must[:12],
    }


def canonical_plan(brief: Mapping[str, Any]) -> tuple[PlannedTask, ...]:
    title = str(brief.get("title") or "game")
    return (
        PlannedTask("director", StudioRole.DIRECTOR, "studio.director", (), f"Direct {title}"),
        PlannedTask("design", StudioRole.DESIGNER, "studio.design", ("director",), "Define the core loop"),
        PlannedTask("systems", StudioRole.SYSTEMS, "studio.systems", ("design",), "Specify mechanics"),
        PlannedTask("level", StudioRole.LEVEL, "studio.level", ("design",), "Lay out spaces"),
        PlannedTask("narrative", StudioRole.NARRATIVE, "studio.narrative", ("design",), "Write beats"),
        PlannedTask("art", StudioRole.ART, "studio.art", ("design",), "List assets"),
        PlannedTask("audio", StudioRole.AUDIO, "studio.audio", ("design",), "List cues"),
        PlannedTask(
            "integrate",
            StudioRole.SYSTEMS,
            "studio.integrate",
            ("systems", "level", "narrative", "art", "audio"),
            "Assemble the playable",
        ),
        PlannedTask("qa", StudioRole.QA, "studio.qa", ("integrate",), "Playtest the loop"),
    )


def plan_brief(
    brief: Mapping[str, Any],
    *,
    model: ModelClient | None = None,
) -> tuple[PlannedTask, ...]:
    """Return the dependency graph for one brief."""
    normalized = normalize_brief(brief)
    fallback = canonical_plan(normalized)
    if model is None:
        return fallback
    try:
        proposed = model.complete(
            role="planner",
            prompt=json.dumps(normalized, sort_keys=True, separators=(",", ":")),
        )
    except Exception:
        return fallback
    accepted = _accept_proposal(proposed, fallback)
    return accepted if accepted is not None else fallback


def _accept_proposal(
    proposed: Mapping[str, Any] | None,
    fallback: tuple[PlannedTask, ...],
) -> tuple[PlannedTask, ...] | None:
    if not isinstance(proposed, Mapping):
        return None
    raw_tasks = proposed.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return None
    try:
        tasks = tuple(PlannedTask.from_dict(item) for item in raw_tasks)
    except (KeyError, TypeError, ValueError):
        return None
    expected = {task.id: task for task in fallback}
    if {task.id for task in tasks} != set(expected):
        return None
    dag = SwarmDag()
    try:
        for task in tasks:
            canonical = expected[task.id]
            if task.role is not canonical.role or task.capability != canonical.capability:
                return None
            if tuple(task.deps) != canonical.deps:
                return None
            dag.submit(task.id, task.capability, {"goal": task.goal}, list(task.deps))
    except Exception:
        return None
    if dag.ready_wave()[0].id != "director":
        return None
    return tasks


def _clean_line(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    lowered = text.lower()
    blocked = (
        "ignore previous",
        "jailbreak",
        "<|system|>",
        "http://",
        "https://",
        "../",
        "subprocess",
        "api_key",
        "password",
        "secret",
        "token",
    )
    if any(marker in lowered for marker in blocked):
        return ""
    return text
