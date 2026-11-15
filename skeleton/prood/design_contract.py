"""Closed, bounded input contract for the offline design campaign.

The campaign produces original design data, not engine qualification. Request
identity includes every admitted knob so replays cannot silently change scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import json

from skeleton.forge.game_design_spec import compile_brief
from skeleton.frontier.payloads import json_snapshot

SCHEMA = "prood.design.campaign.v1"
PHASES = ("world", "narrative", "mechanics", "procedural", "tileset", "assets")
AXES = ("tempo", "risk", "agency", "scarcity", "spectacle", "grind")
THEMES = ("moss", "neon", "ember", "frost")
_MAX = 24


def digest(value: object) -> str:
    raw = json.dumps(json_snapshot(value, max_bytes=2 << 20), sort_keys=True,
                     separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    return sha256(raw).hexdigest()


def text(value, name, maximum):
    if (type(value) is not str or not value.strip() or len(value.encode("utf-8")) > maximum
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise ValueError("invalid " + name)
    return value.strip()


def integer(value, name, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("invalid " + name)
    return value


def unit(value, name):
    if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
        raise ValueError("invalid " + name)
    return float(value)


@dataclass(frozen=True, slots=True)
class DesignRequest:
    build_id: str
    vision: str
    seed: int = 0
    regions: int = 6
    quest_depth: int = 4
    grid_size: int = 11
    theme: str = "moss"
    axes: tuple[tuple[str, float], ...] = ()
    variants: int = 3

    def __post_init__(self):
        object.__setattr__(self, "build_id", text(self.build_id, "build ID", 128))
        object.__setattr__(self, "vision", text(self.vision, "vision", 4000))
        integer(self.seed, "seed", -(1 << 63), (1 << 63)-1)
        integer(self.regions, "region count", 3, _MAX)
        integer(self.quest_depth, "quest depth", 2, _MAX)
        integer(self.grid_size, "grid dimension", 5, 31)
        if self.grid_size % 2 != 1:
            raise ValueError("maze dimension must be odd")
        integer(self.variants, "design variants", 1, 8)
        if type(self.theme) is not str or self.theme not in THEMES:
            raise ValueError("unsupported visual theme")
        if type(self.axes) is not tuple or len(self.axes) > len(AXES):
            raise ValueError("closed tuple of design axes required")
        seen = {}
        for pair in self.axes:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("invalid design axis pair")
            key, value = pair
            if type(key) is not str or key not in AXES or key in seen:
                raise ValueError("unknown or duplicate design axis")
            seen[key] = unit(value, key)
        object.__setattr__(self, "axes", tuple(sorted(seen.items())))
        # Validate the canonical compiler before any durable work is admitted.
        compile_brief(self.vision)

    def context(self):
        spec = compile_brief(self.vision)
        return {"schema": SCHEMA, "build_id": self.build_id, "seed": self.seed,
                "vision": self.vision, "regions": self.regions, "quest_depth": self.quest_depth,
                "grid_size": self.grid_size, "theme": self.theme,
                "axes": dict(self.axes), "variants": self.variants, "spec": spec}


def validate_context(raw: object) -> dict:
    if type(raw) is not dict or raw.get("schema") != SCHEMA:
        raise ValueError("canonical design context required")
    expected = {"schema", "build_id", "seed", "vision", "regions", "quest_depth",
                "grid_size", "theme", "axes", "variants", "spec"}
    if set(raw) != expected or type(raw["axes"]) is not dict:
        raise ValueError("unexpected design context fields")
    req = DesignRequest(raw["build_id"], raw["vision"], raw["seed"], raw["regions"],
                        raw["quest_depth"], raw["grid_size"], raw["theme"],
                        tuple(raw["axes"].items()), raw["variants"])
    canonical = req.context()
    if digest(raw) != digest(canonical):
        raise ValueError("design context or compiler spec differs")
    return canonical
