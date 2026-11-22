"""
Swarm mesh handoff and headless TurnEngine play loop extract-heat-sleep.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

VERBS = ["extract", "heat", "sleep"]


def process(data: dict) -> dict:
    refused = admit("swarm_turn", data)
    if refused:
        return refused
    verb = data.get("verb")
    if verb is None:
        return stamp("swarm_turn", data, {"verbs": VERBS})
    if verb not in VERBS:
        return {
            "ok": False,
            "error": "unknown verb",
            "card": "swarm_turn",
            "verbs": list(VERBS),
        }
    index = VERBS.index(verb)
    return stamp(
        "swarm_turn",
        data,
        {"verbs": VERBS, "verb": verb, "next": VERBS[(index + 1) % len(VERBS)]},
    )
