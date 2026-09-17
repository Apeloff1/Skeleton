"""Named hazards. Enter/tick/leave."""

from __future__ import annotations

from typing import Any


class HazardPackError(ValueError):
    pass


HAZ = (
    "spark_trap", "ash_pit", "fog_bank", "lock_shock", "heat_jet", "extract_hum",
    "shaft_drop", "stair_slip", "bridge_gap", "dead_end", "cycle_loop", "crowd_crush",
    "quiet_ambush", "loud_alarm", "dream_rip", "warp_snap",
)


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HAZ:
        raise HazardPackError(name)
    nxt = dict(state)
    nxt["hazard"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((HAZ.index(name) % 5) - 2)))
    nxt["stored_prose"] = 0
    return nxt


def tick(state: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in HAZ:
        raise HazardPackError(name)
    i = HAZ.index(name)
    nxt = dict(state)
    nxt["hp"] = max(0, int(nxt.get("hp", 40)) - (1 if i % 3 == 0 else 0))
    nxt["alert"] = int(nxt.get("alert", 0)) + (1 if i % 2 == 0 else 0)
    nxt["stored_prose"] = 0
    return nxt


def leave(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HAZ:
        raise HazardPackError(name)
    nxt = dict(state)
    nxt["hazard"] = ""
    nxt["stored_prose"] = 0
    return nxt
