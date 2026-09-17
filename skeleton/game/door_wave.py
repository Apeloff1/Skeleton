"""Wave-4 extra doors."""

from __future__ import annotations

from typing import Any


class DoorWaveError(ValueError):
    pass


DOORS = {f"dr_{i:02d}": i % 3 for i in range(16)}


def make(name: str) -> dict[str, Any]:
    if name not in DOORS:
        raise DoorWaveError(name)
    keys = DOORS[name]
    return {"door": name, "keys": keys, "open": keys == 0, "stored_prose": 0}


def use(door: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    name = str(door.get("door") or "")
    if name not in DOORS:
        raise DoorWaveError(name)
    d, s = dict(door), dict(state)
    need = DOORS[name]
    if (not d.get("open")) and int(s.get("key", 0)) < need:
        raise DoorWaveError("key")
    if not d.get("open"):
        s["key"] = int(s.get("key", 0)) - need
        d["open"] = True
    d["stored_prose"] = 0
    s["stored_prose"] = 0
    return d, s
