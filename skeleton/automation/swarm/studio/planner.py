"""Plan production notes for a compiled design spec.

The canonical graph is deterministic. An injected model may propose the same
graph, and that proposal is used only when every gate matches. Anything else
falls back to the canonical plan. The plan annotates ``skeleton.game_design_spec.v1``.
It does not schedule a second game build.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from skeleton.automation.swarm.dag import SwarmDag
from skeleton.automation.swarm.studio.roles import StudioRole


class PlanError(ValueError):
    """The spec cannot be planned."""


class ModelClient(Protocol):
    def complete(self, *, role: str, prompt: str) -> Mapping[str, Any] | None:
        """Return a task graph, or None to keep the deterministic plan."""


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
    def from_dict(cls, raw: Mapping[str, Any]) -> PlannedTask:
        return cls(
            id=str(raw["id"]),
            role=StudioRole(str(raw["role"])),
            capability=str(raw["capability"]),
            deps=tuple(str(item) for item in raw.get("deps") or ()),
            goal=str(raw.get("goal") or ""),
        )


def canonical_plan(spec: Mapping[str, Any]) -> tuple[PlannedTask, ...]:
    title = str(spec.get("title") or "game")
    return (
        PlannedTask("director", StudioRole.DIRECTOR, "studio.director", (), f"Direct {title}"),
        PlannedTask("design", StudioRole.DESIGNER, "studio.design", ("director",), "Record the core loop"),
        PlannedTask("systems", StudioRole.SYSTEMS, "studio.systems", ("design",), "Name the mechanics"),
        PlannedTask("level", StudioRole.LEVEL, "studio.level", ("design",), "Note the layout"),
        PlannedTask("narrative", StudioRole.NARRATIVE, "studio.narrative", ("design",), "Note the beats"),
        PlannedTask("art", StudioRole.ART, "studio.art", ("design",), "List asset requests"),
        PlannedTask("audio", StudioRole.AUDIO, "studio.audio", ("design",), "List cues"),
    )


def plan_brief(
    spec: Mapping[str, Any],
    *,
    model: ModelClient | None = None,
) -> tuple[PlannedTask, ...]:
    """Return the planning graph for one compiled spec."""
    if not isinstance(spec, Mapping) or spec.get("schema_version") != "skeleton.game_design_spec.v1":
        raise PlanError("planner requires skeleton.game_design_spec.v1")
    fallback = canonical_plan(spec)
    if model is None:
        return fallback
    try:
        proposed = model.complete(
            role="planner",
            prompt=json.dumps(
                {"spec_id": spec.get("spec_id"), "genre": spec.get("genre"), "title": spec.get("title")},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    except Exception:  # noqa: BLE001 — a bad model proposal falls back to the canonical plan
        return fallback
    accepted = _accept_proposal(proposed, fallback)
    return accepted if accepted is not None else fallback


def apply_plan(spec: Mapping[str, Any], artefacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Copy planner notes onto the spec without changing the committed game."""
    enriched = dict(spec)
    director = artefacts.get("director") if isinstance(artefacts.get("director"), Mapping) else {}
    design = artefacts.get("design") if isinstance(artefacts.get("design"), Mapping) else {}
    title = director.get("title")
    if isinstance(title, str) and title.strip():
        enriched["title"] = " ".join(title.split())[:48]
    fantasy = design.get("fantasy")
    if isinstance(fantasy, str) and fantasy.strip():
        enriched["fantasy"] = " ".join(fantasy.split())[:180]
    loop = design.get("core_loop")
    if isinstance(loop, str) and loop.strip():
        enriched["core_loop"] = " ".join(loop.split())[:180]
    notes: dict[str, str] = {}
    pillar = director.get("pillar")
    if isinstance(pillar, str) and pillar.strip():
        notes["pillar"] = " ".join(pillar.split())[:240]
    systems = artefacts.get("systems") if isinstance(artefacts.get("systems"), Mapping) else {}
    mechanics = systems.get("mechanics")
    if isinstance(mechanics, list) and mechanics:
        notes["mechanics"] = ", ".join(str(item) for item in mechanics[:8])[:240]
    level = artefacts.get("level") if isinstance(artefacts.get("level"), Mapping) else {}
    layout = level.get("layout")
    if isinstance(layout, str) and layout.strip():
        notes["layout"] = " ".join(layout.split())[:240]
    narrative = artefacts.get("narrative") if isinstance(artefacts.get("narrative"), Mapping) else {}
    beats = narrative.get("beats")
    if isinstance(beats, list) and beats:
        notes["beats"] = ", ".join(str(item) for item in beats[:6])[:240]
    if notes:
        enriched["production"] = notes
    return enriched


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
    except Exception:  # noqa: BLE001 — a bad model proposal falls back to the canonical plan
        return None
    if dag.ready_wave()[0].id != "director":
        return None
    return tasks
