"""Wave-4 dream beats. Extract-safe."""

from __future__ import annotations

from typing import Any


class DreamWaveError(ValueError):
    pass


NEED = {f"drm_{i:02d}": (4 if i % 2 else 8) for i in range(20)}


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in NEED:
        raise DreamWaveError(name)
    nxt = dict(state)
    if int(nxt.get("sleep", 0)) < NEED[name]:
        raise DreamWaveError("sleep")
    if int(nxt.get("extracted", 0)) > 0:
        raise DreamWaveError("extracted")
    nxt["sleep"] = max(0, int(nxt.get("sleep", 0)) - NEED[name])
    nxt["slept"] = int(nxt.get("slept", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
