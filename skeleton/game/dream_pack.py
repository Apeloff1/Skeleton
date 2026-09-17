"""Named sleep/dream beats. Extract-safe."""

from __future__ import annotations

from typing import Any


class DreamPackError(ValueError):
    pass


NEED = {
    "doze": 4, "nap": 4, "deep": 8, "fever": 4, "nightmare": 8,
    "lucid": 4, "blank": 4, "loop": 8, "extract_dream": 8, "heat_dream": 4,
    "fog_dream": 4, "lock_dream": 4, "hunt_dream": 4, "save_dream": 4,
    "quest_dream": 4, "warp_dream": 8, "mesh_dream": 4, "doctor_dream": 4,
    "clip_dream": 4, "seal_dream": 8,
}


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in NEED:
        raise DreamPackError(name)
    nxt = dict(state)
    need = NEED[name]
    if int(nxt.get("sleep", 0)) < need:
        raise DreamPackError("sleep")
    if int(nxt.get("extracted", 0)) > 0:
        raise DreamPackError("extracted")
    nxt["sleep"] = max(0, int(nxt.get("sleep", 0)) - need)
    nxt["slept"] = int(nxt.get("slept", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
