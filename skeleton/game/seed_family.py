"""Deterministic seed families for arena batches. No uuid. No wall clock."""

from __future__ import annotations

import hashlib
from typing import Any


MAX_FAMILY = 32


class SeedFamilyError(ValueError):
    """Seed family contract violation."""


def _material(parent: int | str, index: int) -> int:
    text = f"{parent}:{index}:family".encode("utf-8")
    return int.from_bytes(hashlib.sha256(text).digest()[:8], "big")


def family(parent: int | str, size: int) -> list[int]:
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise SeedFamilyError("family size must be a positive integer")
    if size > MAX_FAMILY:
        raise SeedFamilyError("family exceeds cap")
    if isinstance(parent, bool) or not isinstance(parent, (int, str)):
        raise SeedFamilyError("parent seed must be int or str")
    if isinstance(parent, str) and not parent.strip():
        raise SeedFamilyError("parent seed must not be empty")
    return [_material(parent, index) for index in range(size)]


def family_card(parent: int | str, size: int) -> dict[str, Any]:
    seeds = family(parent, size)
    return {
        "kind": "seed_family",
        "parent": parent,
        "size": size,
        "seeds": seeds,
        "stored_prose": 0,
    }
