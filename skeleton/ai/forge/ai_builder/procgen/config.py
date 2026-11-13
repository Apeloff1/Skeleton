"""One config object for the whole pipeline, buildable from plain data."""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any, Mapping

from .bsp import BspConfig
from .encounters import EncounterConfig, PacingCurve
from .errors import ProcgenError
from .graph_rooms import GraphConfig
from .loot import LootConfig
from .metrics import LayoutLimits
from .terrain import TerrainConfig

DUNGEON_METHODS = ("bsp", "graph")


@dataclass(frozen=True)
class ProcgenConfig:
    dungeon: str = "bsp"
    bsp: BspConfig = field(default_factory=BspConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    terrain: TerrainConfig = field(default_factory=TerrainConfig)
    encounters: EncounterConfig = field(default_factory=EncounterConfig)
    loot: LootConfig = field(default_factory=LootConfig)
    locks: int = 2
    max_attempts: int = 8           # re-roll the layout if it is too small for the locks
    min_rooms: int = 4
    level_prefix: str = "pg_"
    system: str = "combat"
    replace_levels: bool = True
    prune_unused: bool = True        # with replace_levels: drop scenes/assets the old levels used
    limits: LayoutLimits = field(default_factory=LayoutLimits)
    strict_locks: bool = False       # raise instead of recording a lock shortfall

    def __post_init__(self) -> None:
        if self.dungeon not in DUNGEON_METHODS:
            raise ProcgenError(f"dungeon must be one of {DUNGEON_METHODS}")
        if not 0 <= self.locks <= 8 or not 1 <= self.max_attempts <= 64 or not 2 <= self.min_rooms <= 64:
            raise ProcgenError("locks in [0, 8], max_attempts in [1, 64], min_rooms in [2, 64]")
        if not self.level_prefix.isidentifier():
            raise ProcgenError("level_prefix must be an identifier")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ProcgenConfig":
        """Build from nested dicts, e.g. ``plan["procgen_config"]``; unknown keys are rejected."""
        if not data:
            return cls()
        if not isinstance(data, Mapping):
            raise ProcgenError("procgen config must be a mapping")
        nested = {"bsp": BspConfig, "graph": GraphConfig, "terrain": TerrainConfig,
                  "encounters": EncounterConfig, "loot": LootConfig, "limits": LayoutLimits}
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ProcgenError(f"unknown procgen config keys {sorted(unknown)}")
        kwargs: dict[str, Any] = {}
        for k, v in data.items():
            if k in nested:
                if not isinstance(v, Mapping):
                    raise ProcgenError(f"procgen config {k!r} must be a mapping")
                sub = dict(v)
                if k == "encounters" and "pacing" in sub:
                    sub["pacing"] = _build(PacingCurve, sub["pacing"], "encounters.pacing")
                if k in ("encounters", "terrain") and ({"roles", "boss", "biomes"} & set(sub)):
                    raise ProcgenError("roles/boss/biomes must be passed as objects, not plain data")
                kwargs[k] = _build(nested[k], sub, k)
            else:
                kwargs[k] = v
        return cls(**kwargs)

    def with_(self, **changes: Any) -> "ProcgenConfig":
        return replace(self, **changes)

    def as_dict(self) -> dict:
        return {"dungeon": self.dungeon, "locks": self.locks, "min_rooms": self.min_rooms,
                "max_attempts": self.max_attempts, "level_prefix": self.level_prefix, "system": self.system,
                "terrain": self.terrain.as_dict(),
                "layout": _plain(self.bsp if self.dungeon == "bsp" else self.graph),
                "pacing": _plain(self.encounters.pacing), "encounter_cap": self.encounters.cap,
                "loot": _plain(self.loot), "limits": self.limits.as_dict(), "strict_locks": self.strict_locks}


def _build(kind, data: Mapping[str, Any], label: str):
    names = {f.name for f in fields(kind)}
    bad = set(data) - names
    if bad:
        raise ProcgenError(f"unknown {label} keys {sorted(bad)}")
    try:
        return kind(**data)
    except TypeError as exc:  # pragma: no cover - dataclass arg errors
        raise ProcgenError(f"bad {label}: {exc}") from exc


def _plain(obj) -> dict:
    return {f.name: getattr(obj, f.name) for f in fields(obj)}
