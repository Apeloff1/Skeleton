"""Wave-4 compact tables. Same names as the local 9k dump."""

from __future__ import annotations

from typing import Any


class Wave4Error(ValueError):
    pass


WEATHER = {f"wx_{i:02d}": ((i % 5) - 2, i % 3) for i in range(40)}
LOCKS = {f"lock_{i:02d}": 1 + (i % 3) for i in range(36)}
HEAT = {f"src_{i:02d}": 1 + (i % 4) for i in range(32)}


def weather_tick(name: str, node: dict[str, Any], t: int) -> dict[str, Any]:
    if name not in WEATHER:
        raise Wave4Error(name)
    dh, df = WEATHER[name]
    nxt = dict(node)
    nxt["wx"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + dh + (t % 3) - 1))
    nxt["fog"] = max(0, min(8, int(nxt.get("fog", 0)) + df - 1))
    nxt["stored_prose"] = 0
    return nxt


def lock_open(name: str, state: dict[str, Any]) -> dict[str, Any]:
    if name not in LOCKS:
        raise Wave4Error(name)
    need = LOCKS[name]
    nxt = dict(state)
    if int(nxt.get("key", 0)) < need:
        raise Wave4Error("key")
    nxt["key"] = int(nxt.get("key", 0)) - need
    nxt["opened"] = name
    nxt["stored_prose"] = 0
    return nxt


def heat_emit(name: str, node: dict[str, Any]) -> dict[str, Any]:
    if name not in HEAT:
        raise Wave4Error(name)
    nxt = dict(node)
    nxt["src"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + HEAT[name])
    nxt["stored_prose"] = 0
    return nxt
