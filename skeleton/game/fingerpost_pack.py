"""Named fingerposts."""

from __future__ import annotations

from typing import Any


class FingerpostPackError(ValueError):
    pass


FINGER = tuple(f"fp_{i:02d}" for i in range(8))


def set_finger(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FINGER:
        raise FingerpostPackError(name)
    nxt = dict(node)
    nxt["fingerpost"] = name
    nxt["stored_prose"] = 0
    return nxt
