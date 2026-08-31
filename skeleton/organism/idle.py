"""Dream on idle — SleepCycle mouth × DreamBrain nucleus.

A step is idle-dreamable when the operator did not ask for sleep and
N steps have passed since the last consolidation. Default N=4.
Mouth sleep_cycle runs only if the neo exposes it. DreamBrain always
can.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


CADENCE = 4


def due(steps: int, last_dream_step: int, *, cadence: int = CADENCE) -> bool:
    return steps > 0 and (steps - last_dream_step) >= cadence


def run(galaxy, neo: Any = None, *, replay_k: int = 6) -> Dict[str, Any]:
    mouth = None
    if neo is not None and hasattr(neo, "sleep_cycle"):
        try:
            mouth = neo.sleep_cycle(n=4)
        except Exception as exc:
            mouth = {"ok": 0, "error": type(exc).__name__}
    dream = galaxy.dream.sleep(replay_k=replay_k)
    return {
        "kind": "idle-dream",
        "mouth": mouth,
        "dream": dream,
        "stored_prose": 0,
    }
