"""Typed, fail-closed game-creation tool fabric for Jeeves, Dragon and companion.

This module is a capability registry and execution *planning* boundary. A
registered executable is never itself an authorization to call it. External
connectors, engines, plugins and models stay unavailable until a separate
operator-controlled adapter both installs and authorizes them.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import islice
import re
from typing import Iterable, Mapping

from .contracts import canonical_digest


class ToolFabricError(ValueError):
    """Untrusted, unsupported or unauthorized game-building tool request."""


class Actor(str, Enum):
    JEEVES = "jeeves"
    DRAGON = "dragon"
    COMPANION = "companion"
    MIRROR = "mirror_room"
    OPERATOR = "operator"


class Phase(str, Enum):
    RESEARCH = "research"
    ORIGINAL = "original"
    STEPPING_STONE = "stepping_stone"
    CONSUMER = "consumer"
    REVIEW = "review"


class Access(str, Enum):
    BUILTIN = "builtin"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    tool_id: str
    capability: str
    phases: frozenset[Phase]
    actors: frozenset[Actor]
    access: Access
    resource_units: int
    side_effects: frozenset[str]
    license_id: str
    adapter_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_id, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{2,95}", self.tool_id):
            raise ToolFabricError("invalid tool identifier")
        if not isinstance(self.capability, str) or not 1 <= len(self.capability) <= 160:
            raise ToolFabricError("invalid capability label")
        if not self.phases or not isinstance(self.phases, frozenset) or any(
            not isinstance(x, Phase) for x in self.phases
        ):
            raise ToolFabricError("invalid tool phases")
        if not self.actors or not isinstance(self.actors, frozenset) or any(
            not isinstance(x, Actor) for x in self.actors
        ):
            raise ToolFabricError("invalid tool actor authority")
        if not isinstance(self.access, Access):
            raise ToolFabricError("invalid tool accessibility")
        if type(self.resource_units) is not int or not 1 <= self.resource_units <= 10000:
            raise ToolFabricError("invalid bounded tool resource cost")
        if not isinstance(self.side_effects, frozenset) or any(
            x not in {"filesystem", "process", "network", "publication", "training"}
            for x in self.side_effects
        ):
            raise ToolFabricError("unrecognized tool side effects")
        if not isinstance(self.license_id, str) or not self.license_id.strip():
            raise ToolFabricError("tool license disclosure required")
        if self.access is Access.EXTERNAL and (
            not isinstance(self.adapter_digest, str)
            or not re.fullmatch("[0-9a-f]{64}", self.adapter_digest)
        ):
            raise ToolFabricError("external adapter needs a pinned implementation digest")
        if self.access is Access.BUILTIN and self.adapter_digest is not None:
            raise ToolFabricError("builtins have no third-party adapter")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "tool_id": self.tool_id,
            "capability": self.capability,
            "phases": sorted(x.value for x in self.phases),
            "actors": sorted(x.value for x in self.actors),
            "access": self.access.value,
            "resource_units": self.resource_units,
            "side_effects": sorted(self.side_effects),
            "license_id": self.license_id,
            "adapter_digest": self.adapter_digest,
        }


@dataclass(frozen=True, slots=True)
class ToolRequest:
    actor: Actor
    phase: Phase
    tool_id: str
    input_digest: str
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, Actor) or not isinstance(self.phase, Phase):
            raise ToolFabricError("typed actor and pipeline phase required")
        if not isinstance(self.tool_id, str) or not self.tool_id:
            raise ToolFabricError("tool identifier required")
        if not isinstance(self.input_digest, str) or not re.fullmatch("[0-9a-f]{64}", self.input_digest):
            raise ToolFabricError("content-addressed input required")
        if not isinstance(self.rationale, str) or not 3 <= len(self.rationale) <= 300:
            raise ToolFabricError("explicit bounded rationale required")

    def to_payload(self) -> dict[str, object]:
        return {
            "actor": self.actor.value,
            "phase": self.phase.value,
            "tool_id": self.tool_id,
            "input_digest": self.input_digest,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class ToolPlan:
    requests: tuple[ToolRequest, ...]
    tool_digests: tuple[str, ...]
    resource_units: int
    external_blocked: tuple[str, ...]
    write_authorized: bool

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.tool_plan.v1",
            "requests": [r.to_payload() for r in self.requests],
            "tool_digests": list(self.tool_digests),
            "resource_units": self.resource_units,
            "external_blocked": list(self.external_blocked),
            "write_authorized": self.write_authorized,
            "executes_external_tools": False,
            "publication_authority": False,
        }


def _builtin(tool_id: str, capability: str, phases: tuple[Phase, ...],
             actors: tuple[Actor, ...], cost: int, effects: tuple[str, ...] = ()) -> ToolSpec:
    return ToolSpec(tool_id, capability, frozenset(phases),
                    frozenset(actors), Access.BUILTIN, cost,
                    frozenset(effects), "project-original")


BUILD = (Actor.JEEVES, Actor.DRAGON, Actor.COMPANION, Actor.OPERATOR)
AUDIT = (Actor.JEEVES, Actor.MIRROR, Actor.OPERATOR)
ALL_PHASES = tuple(Phase)
BUILTIN_TOOLS = (
    _builtin("knowledge.search", "search locally reviewed game-building knowledge",
             (Phase.RESEARCH, Phase.ORIGINAL), BUILD, 2),
    _builtin("rights.check", "check source rights using canonical rights governance",
             (Phase.RESEARCH, Phase.REVIEW, Phase.CONSUMER), AUDIT, 3),
    _builtin("world.generate", "generate original bounded, replay-proved game levels",
             (Phase.ORIGINAL, Phase.STEPPING_STONE), BUILD, 15),
    _builtin("world.authored", "validate human-authored game editor geometry",
             (Phase.ORIGINAL, Phase.STEPPING_STONE), BUILD, 10),
    _builtin("world.tiled", "import original numeric geometry from local Tiled JSON and prove gameplay",
             (Phase.ORIGINAL,), (Actor.JEEVES, Actor.DRAGON, Actor.OPERATOR), 13),
    _builtin("game.simulate", "execute deterministic Python game-state transitions",
             (Phase.STEPPING_STONE, Phase.REVIEW), (*BUILD, Actor.MIRROR), 5),
    _builtin("game.browser", "render an offline browser-playable original game",
             (Phase.STEPPING_STONE, Phase.CONSUMER), BUILD, 9),
    _builtin("game.godot", "render Godot 4 source project from same world",
             (Phase.STEPPING_STONE, Phase.CONSUMER), BUILD, 10),
    _builtin("game.editor", "provide an offline map painting and editing surface",
             (Phase.ORIGINAL, Phase.STEPPING_STONE), BUILD, 6),
    _builtin("game.native_recipe", "generate local Godot export instructions, not launch a build",
             (Phase.CONSUMER,), (Actor.JEEVES, Actor.OPERATOR), 2),
    _builtin("mirror.fuzz", "run deterministic adversarial gameplay and proof probes",
             (Phase.REVIEW,), AUDIT, 22),
    _builtin("mirror.originality", "inspect rights/similarity alerts without copying sources",
             (Phase.REVIEW,), AUDIT, 8),
    _builtin("release.assess", "evaluate consumer release evidence and blocked certifications",
             (Phase.CONSUMER, Phase.REVIEW), AUDIT, 7),
    _builtin("companion.practice", "generate original training-game variation proposals",
             (Phase.ORIGINAL, Phase.STEPPING_STONE), BUILD, 5),
    _builtin("package.source", "assemble content-addressed source project deliverables",
             (Phase.CONSUMER,), (Actor.JEEVES, Actor.OPERATOR), 10, ("filesystem",)),
)


class ToolFabric:
    """Deterministic discovery/planning. External adapters cannot run here."""

    def __init__(self, additions: Iterable[ToolSpec] = ()) -> None:
        external = tuple(islice(additions, 2049))
        if len(external) > 2048:
            raise ToolFabricError("game tool catalog exceeds 2048 typed adapters")
        values = [*BUILTIN_TOOLS, *external]
        if any(not isinstance(value, ToolSpec) for value in values):
            raise ToolFabricError("typed capability descriptors required")
        names = [value.tool_id for value in values]
        if len(names) != len(set(names)):
            raise ToolFabricError("tool ID collision with built-in or external tools")
        self._tools = {value.tool_id: value for value in values}

    def discover(self, *, actor: Actor, phase: Phase) -> tuple[ToolSpec, ...]:
        if not isinstance(actor, Actor) or not isinstance(phase, Phase):
            raise ToolFabricError("typed role and phase required")
        return tuple(
            t for t in sorted(self._tools.values(), key=lambda t: t.tool_id)
            if actor in t.actors and phase in t.phases
        )

    def plan(
        self, requests: Iterable[ToolRequest], *,
        authorized: bool, max_resource_units: int = 500,
        enabled_external: Mapping[str, str] | None = None,
        allow_filesystem_write: bool = False,
    ) -> ToolPlan:
        if type(authorized) is not bool or not authorized:
            raise PermissionError("operator approval required for tool planning")
        if type(max_resource_units) is not int or not 1 <= max_resource_units <= 10000:
            raise ToolFabricError("invalid tool work budget")
        if type(allow_filesystem_write) is not bool:
            raise ToolFabricError("typed filesystem approval flag required")
        if enabled_external is None:
            enabled_external = {}
        if not isinstance(enabled_external, dict) or any(
            not isinstance(k, str) or not isinstance(v, str)
            for k, v in enabled_external.items()
        ):
            raise ToolFabricError("external capability grants must be keyed by pinned digests")
        # Never materialize an unbounded producer-controlled iterable.
        rows = tuple(islice(requests, 129))
        if len(rows) > 128 or any(not isinstance(r, ToolRequest) for r in rows):
            raise ToolFabricError("unbounded or invalid tool requests")
        blocked = []
        digests = []
        cost = 0
        for request in rows:
            tool = self._tools.get(request.tool_id)
            if tool is None:
                raise ToolFabricError("tool is not registered")
            if request.actor not in tool.actors or request.phase not in tool.phases:
                raise ToolFabricError("tool request crosses role/phase boundary")
            if "publication" in tool.side_effects or "training" in tool.side_effects:
                raise ToolFabricError("publication/training requires a separate approval system")
            if tool.access is Access.EXTERNAL:
                if enabled_external.get(tool.tool_id) != tool.adapter_digest:
                    blocked.append(tool.tool_id)
            if "filesystem" in tool.side_effects and not allow_filesystem_write:
                blocked.append(tool.tool_id)
            digests.append(tool.digest)
            cost += tool.resource_units
            if cost > max_resource_units:
                raise ToolFabricError("tool plan exceeds resource budget")
        return ToolPlan(rows, tuple(digests), cost, tuple(sorted(set(blocked))),
                        allow_filesystem_write)


__all__ = [
    "Access", "Actor", "Phase", "ToolSpec", "ToolRequest", "ToolPlan",
    "ToolFabric", "ToolFabricError", "BUILTIN_TOOLS",
]
