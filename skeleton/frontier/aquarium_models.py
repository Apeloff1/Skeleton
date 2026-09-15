"""Validated value models for the promoted aquarium policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Mapping


def text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be non-empty and normalized")
    return value


def count(value: object, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < (1 if positive else 0):
        raise ValueError(f"{name} is out of range")
    return value


def aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def counts(values: Mapping[str, int], name: str) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return {text(key, f"{name} key"): count(value, f"{name} count") for key, value in values.items()}


@dataclass(frozen=True, slots=True)
class AquariumPosition:
    x: int
    y: int

    def __post_init__(self) -> None:
        x, y = count(self.x, "position x"), count(self.y, "position y")
        if x > 100 or y > 100:
            raise ValueError("position coordinates must be within 0..100")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)


@dataclass(frozen=True, slots=True)
class AquariumTankSpec:
    id: str
    name: str
    capacity: int
    unlock_level: int
    decorations_allowed: int
    cost: Mapping[str, int] = field(default_factory=dict)
    special: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", text(self.id, "tank id"))
        object.__setattr__(self, "name", text(self.name, "tank name"))
        object.__setattr__(self, "capacity", count(self.capacity, "tank capacity", positive=True))
        object.__setattr__(self, "unlock_level", count(self.unlock_level, "tank unlock level", positive=True))
        object.__setattr__(self, "decorations_allowed", count(self.decorations_allowed, "decoration limit"))
        object.__setattr__(self, "cost", counts(self.cost, "tank cost"))
        if not isinstance(self.special, bool):
            raise TypeError("tank special must be boolean")


@dataclass(frozen=True, slots=True)
class DecorationSpec:
    id: str
    name: str
    category: str
    cost: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", text(self.id, "decoration id"))
        object.__setattr__(self, "name", text(self.name, "decoration name"))
        object.__setattr__(self, "category", text(self.category, "decoration category").lower())
        object.__setattr__(self, "cost", counts(self.cost, "decoration cost"))


@dataclass(frozen=True, slots=True)
class DisplayFish:
    id: str
    name: str
    species: str
    size: float
    position: AquariumPosition
    traits: Mapping[str, Any] = field(default_factory=dict)
    color: str = "#4A90D9"
    added_at: datetime | None = None

    def __post_init__(self) -> None:
        for attr in ("id", "name", "species", "color"):
            object.__setattr__(self, attr, text(getattr(self, attr), f"fish {attr}"))
        if isinstance(self.size, bool) or not isinstance(self.size, (int, float)):
            raise TypeError("fish size must be numeric")
        size = float(self.size)
        if not math.isfinite(size) or size < 0:
            raise ValueError("fish size must be finite and nonnegative")
        object.__setattr__(self, "size", size)
        if not isinstance(self.position, AquariumPosition):
            raise TypeError("fish position must be AquariumPosition")
        if not isinstance(self.traits, Mapping):
            raise TypeError("fish traits must be a mapping")
        object.__setattr__(self, "traits", dict(self.traits))
        if self.added_at is not None:
            object.__setattr__(self, "added_at", aware(self.added_at, "fish added_at"))
