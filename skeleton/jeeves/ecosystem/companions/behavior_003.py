"""Companion behavior 003.
"""
from __future__ import annotations

BEHAVIOR = "companion_003"

def decide(threat: float, loyalty: float = 0.8) -> str:
    if threat > 0.8:
        return "defend"
    if loyalty > 0.7:
        return "follow"
    return "idle"

def act(brief: str) -> dict:
    if not brief:
        return {"ok": False, "reason": "empty"}
    return {"ok": True, "behavior": BEHAVIOR, "action": decide(0.3), "brief": brief[:120]}
