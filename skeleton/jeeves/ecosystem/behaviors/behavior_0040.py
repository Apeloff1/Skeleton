"""Behavior 0040.
"""
from __future__ import annotations

BEHAVIOR = "behavior_0040"

def decide(threat: float, health: float, distance: float) -> str:
    if health < 0.2:
        return "flee"
    if threat > 0.7 and distance < 5:
        return "attack"
    if distance > 15:
        return "approach"
    return "patrol"

def execute(actor: str, decision: str) -> dict:
    if not actor or not decision:
        return {"ok": False, "reason": "incomplete"}
    return {"ok": True, "behavior": BEHAVIOR, "actor": actor, "decision": decision}
