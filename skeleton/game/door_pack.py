"""Named door machines. Key consume. Fail-closed."""

from __future__ import annotations

from typing import Any


class DoorPackError(ValueError):
    pass


DOORS: dict[str, int] = {
    "wood": 0, "iron": 1, "vent": 0, "shaft": 0, "extract": 2, "lockbox": 1,
    "fogdoor": 0, "heatgate": 0, "cell": 1, "stair": 0, "bridge": 0, "cycle": 0,
    "dead": 3, "dream": 0, "seal": 2, "warp": 1,
}


def make(name: str) -> dict[str, Any]:
    if name not in DOORS:
        raise DoorPackError(name)
    keys = DOORS[name]
    return {"door": name, "keys": keys, "locked": keys > 0, "open": keys == 0, "stored_prose": 0}


def use(door: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    name = str(door.get("door") or "")
    if name not in DOORS:
        raise DoorPackError(name)
    d, s = dict(door), dict(state)
    need = int(d.get("keys", DOORS[name]))
    if d.get("locked") and int(s.get("key", 0)) < need:
        raise DoorPackError("key")
    if d.get("locked"):
        s["key"] = int(s.get("key", 0)) - need
        d["locked"] = False
    d["open"] = True
    d["stored_prose"] = 0
    s["stored_prose"] = 0
    return d, s
