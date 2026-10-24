"""skeleton/gameforge/eras.py

Era registry and binding. An era fixes the palette, tech level and allowed
asset kinds a game may use; every step must be bound to the same era.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

from .errors import EraBindingError, InputError

DEFAULT_ERA = "HOUSE_ERA"


@dataclass(frozen=True)
class Era:
    key: str
    label: str
    tech_level: int
    palette: Tuple[str, ...]
    asset_kinds: FrozenSet[str]
    max_entities: int = 512

    def allows(self, kind: str) -> bool:
        return kind in self.asset_kinds

    def to_dict(self) -> Dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "tech_level": self.tech_level,
            "palette": list(self.palette),
            "asset_kinds": sorted(self.asset_kinds),
            "max_entities": self.max_entities,
        }


_BASE_KINDS = frozenset({"sprite", "tile", "sound", "music", "script", "level"})

BUILTIN_ERAS: Mapping[str, Era] = {
    "HOUSE_ERA": Era("HOUSE_ERA", "House style", 3, ("#1b1b1b", "#e0e0e0", "#c0392b"), _BASE_KINDS | {"model"}, 1024),
    "PIXEL_8BIT": Era("PIXEL_8BIT", "8-bit pixel", 1, ("#000000", "#ffffff", "#880000", "#aaffee"), _BASE_KINDS, 256),
    "PIXEL_16BIT": Era("PIXEL_16BIT", "16-bit pixel", 2, ("#101020", "#f0f0f0", "#3050c0", "#c03030"), _BASE_KINDS, 512),
    "LOWPOLY_3D": Era("LOWPOLY_3D", "Low-poly 3D", 4, ("#202830", "#d8d0c0", "#60a040"), _BASE_KINDS | {"model", "shader"}, 2048),
}


@dataclass
class EraRegistry:
    eras: Dict[str, Era] = field(default_factory=lambda: dict(BUILTIN_ERAS))

    def register(self, era: Era) -> None:
        """Extend-only: an existing key cannot be redefined."""
        if not era.key or not era.key.replace("_", "").isalnum():
            raise InputError(f"invalid era key {era.key!r}")
        if era.key in self.eras and self.eras[era.key] != era:
            raise EraBindingError(f"era {era.key} already registered with a different definition")
        if era.max_entities <= 0:
            raise InputError("era.max_entities must be positive")
        self.eras[era.key] = era

    def get(self, key: str) -> Era:
        try:
            return self.eras[key]
        except KeyError:
            raise EraBindingError(f"unknown era {key!r}", detail={"known": sorted(self.eras)}) from None

    def keys(self) -> Tuple[str, ...]:
        return tuple(sorted(self.eras))


@dataclass
class EraBinding:
    """Tracks which era each step was bound to; refuses drift."""

    era: Era
    bound: Dict[str, str] = field(default_factory=dict)

    def bind(self, step: str, era_key: Optional[str] = None) -> Era:
        key = era_key or self.era.key
        if key != self.era.key:
            raise EraBindingError(
                f"step {step} bound to {key} but run is bound to {self.era.key}",
                step=step,
                detail={"expected": self.era.key, "got": key},
            )
        self.bound[step] = key
        return self.era

    def require_asset(self, step: str, kind: str) -> None:
        if not self.era.allows(kind):
            raise EraBindingError(f"asset kind {kind!r} not allowed in era {self.era.key}", step=step, detail={"kind": kind})
