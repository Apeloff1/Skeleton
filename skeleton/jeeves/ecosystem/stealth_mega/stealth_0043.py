"""Stealth mega 0043.
"""
from __future__ import annotations

ID = "stealth_mega_0043"

def decide(threat: float = 0.5, health: float = 1.0) -> str:
    if health < 0.2:
        return "flee"
    if threat > 0.7:
        return "attack"
    return "patrol"

def execute(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "decision": decide()}
