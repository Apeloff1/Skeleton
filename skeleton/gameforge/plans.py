"""skeleton/gameforge/plans.py

Typed plans produced and consumed by the 7 conductor steps.
All plans are frozen dataclasses with ``to_dict`` for deterministic hashing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple

from .errors import InputError, PlanError

STEPS: Tuple[str, ...] = ("vision", "snowball", "prototype", "mass_forge", "world", "cockpit", "export")
GENRES = frozenset({"platformer", "puzzle", "rpg", "shooter", "strategy", "racing", "adventure", "sandbox"})
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _todict(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, tuple):
        return [_todict(x) for x in obj]
    return obj


class _Plan:
    def to_dict(self) -> Dict[str, Any]:
        return {k: _todict(getattr(self, k)) for k in self.__dataclass_fields__}  # type: ignore[attr-defined]


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:64]
    if not s:
        raise InputError("title produces empty game id")
    return s


@dataclass(frozen=True)
class VisionRequest(_Plan):
    title: str
    pitch: str
    genre: str
    era: str = "HOUSE_ERA"
    pillars: Tuple[str, ...] = ()
    target_minutes: int = 10

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "VisionRequest":
        if not isinstance(data, Mapping):
            raise InputError("vision request must be a mapping")
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise InputError(f"unknown vision fields {sorted(unknown)}")
        try:
            return cls(
                title=str(data["title"]),
                pitch=str(data["pitch"]),
                genre=str(data["genre"]),
                era=str(data.get("era", "HOUSE_ERA")),
                pillars=tuple(str(p) for p in data.get("pillars", ())),
                target_minutes=int(data.get("target_minutes", 10)),
            )
        except KeyError as exc:
            raise InputError(f"missing vision field {exc.args[0]}") from None
        except (TypeError, ValueError) as exc:
            raise InputError(f"bad vision field: {exc}") from None


@dataclass(frozen=True)
class VisionPlan(_Plan):
    game_id: str
    title: str
    pitch: str
    genre: str
    era: str
    pillars: Tuple[str, ...]
    target_minutes: int

    def validate(self) -> None:
        if not _ID_RE.match(self.game_id):
            raise PlanError(f"invalid game_id {self.game_id!r}", step="vision")
        if self.genre not in GENRES:
            raise PlanError(f"unsupported genre {self.genre!r}", step="vision", detail={"genres": sorted(GENRES)})
        if not (1 <= self.target_minutes <= 600):
            raise PlanError("target_minutes out of range 1..600", step="vision")
        if not (1 <= len(self.pillars) <= 5):
            raise PlanError("vision needs 1..5 pillars", step="vision")
        if len(set(self.pillars)) != len(self.pillars):
            raise PlanError("duplicate pillars", step="vision")


@dataclass(frozen=True)
class Feature(_Plan):
    key: str
    pillar: str
    priority: int  # 1 = must, 2 = should, 3 = could
    cost: int


@dataclass(frozen=True)
class SnowballPlan(_Plan):
    game_id: str
    core_loop: Tuple[str, ...]
    features: Tuple[Feature, ...]

    def validate(self, vision: VisionPlan) -> None:
        if len(self.core_loop) < 2:
            raise PlanError("core loop needs at least 2 beats", step="snowball")
        keys = [f.key for f in self.features]
        if len(set(keys)) != len(keys):
            raise PlanError("duplicate feature keys", step="snowball")
        for f in self.features:
            if f.pillar not in vision.pillars:
                raise PlanError(f"feature {f.key} references unknown pillar {f.pillar}", step="snowball")
            if f.priority not in (1, 2, 3) or f.cost <= 0:
                raise PlanError(f"feature {f.key} has bad priority/cost", step="snowball")
        if not any(f.priority == 1 for f in self.features):
            raise PlanError("snowball needs at least one must-have feature", step="snowball")


@dataclass(frozen=True)
class Mechanic(_Plan):
    key: str
    feature: str
    verbs: Tuple[str, ...]


@dataclass(frozen=True)
class PrototypePlan(_Plan):
    game_id: str
    mechanics: Tuple[Mechanic, ...]
    playable_seconds: int

    def validate(self, snowball: SnowballPlan) -> None:
        musts = {f.key for f in snowball.features if f.priority == 1}
        covered = {m.feature for m in self.mechanics}
        missing = musts - covered
        if missing:
            raise PlanError(f"prototype misses must-have features {sorted(missing)}", step="prototype")
        if self.playable_seconds <= 0:
            raise PlanError("prototype must be playable", step="prototype")


@dataclass(frozen=True)
class AssetSpec(_Plan):
    path: str
    kind: str
    size: int
    tags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MassPlan(_Plan):
    game_id: str
    assets: Tuple[AssetSpec, ...]
    budget_bytes: int
    clipped: Tuple[str, ...] = ()  # paths dropped to meet budget

    @property
    def total_bytes(self) -> int:
        return sum(a.size for a in self.assets)

    def validate(self) -> None:
        paths = [a.path for a in self.assets]
        if len(set(paths)) != len(paths):
            raise PlanError("duplicate asset paths", step="mass_forge")
        for p in paths:
            if p.startswith("/") or ".." in p.split("/") or "\\" in p:
                raise PlanError(f"unsafe asset path {p!r}", step="mass_forge")
        if list(paths) != sorted(paths):
            raise PlanError("assets must be sorted by path", step="mass_forge")


@dataclass(frozen=True)
class Region(_Plan):
    key: str
    neighbors: Tuple[str, ...]
    entities: int


@dataclass(frozen=True)
class WorldPlan(_Plan):
    game_id: str
    seed: int
    regions: Tuple[Region, ...]
    start: str

    def validate(self, max_entities: int) -> None:
        keys = {r.key for r in self.regions}
        if self.start not in keys:
            raise PlanError("world start region missing", step="world")
        for r in self.regions:
            for n in r.neighbors:
                if n not in keys:
                    raise PlanError(f"region {r.key} links unknown {n}", step="world")
        # reachability
        adj = {r.key: set(r.neighbors) for r in self.regions}
        for r in self.regions:
            for n in r.neighbors:
                adj[n].add(r.key)
        seen, todo = set(), [self.start]
        while todo:
            k = todo.pop()
            if k in seen:
                continue
            seen.add(k)
            todo.extend(sorted(adj[k] - seen))
        if seen != keys:
            raise PlanError(f"unreachable regions {sorted(keys - seen)}", step="world")
        total = sum(r.entities for r in self.regions)
        if total > max_entities:
            raise PlanError(f"world has {total} entities > era max {max_entities}", step="world")


@dataclass(frozen=True)
class Control(_Plan):
    action: str
    binding: str


@dataclass(frozen=True)
class CockpitPlan(_Plan):
    game_id: str
    controls: Tuple[Control, ...]
    hud: Tuple[str, ...]
    accessibility: Tuple[str, ...]

    def validate(self, prototype: PrototypePlan) -> None:
        bindings = [c.binding for c in self.controls]
        if len(set(bindings)) != len(bindings):
            raise PlanError("conflicting control bindings", step="cockpit")
        verbs = {v for m in prototype.mechanics for v in m.verbs}
        actions = {c.action for c in self.controls}
        if verbs - actions:
            raise PlanError(f"verbs without controls {sorted(verbs - actions)}", step="cockpit")
        if "remappable_controls" not in self.accessibility:
            raise PlanError("cockpit must support remappable controls", step="cockpit")


@dataclass(frozen=True)
class ExportPlan(_Plan):
    game_id: str
    target: str
    files: Tuple[str, ...]


EXPORT_TARGETS = frozenset({"web", "desktop", "bundle"})
