"""Named drifts."""

from __future__ import annotations

from typing import Any


class DriftPackError(ValueError):
    pass


DRIFT = tuple(f"dr_{i:02d}" for i in range(12))


def punch(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DRIFT:
        raise DriftPackError(name)
    nxt = dict(state)
    nxt["drift"] = name
    nxt["hole"] = int(nxt.get("hole", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
