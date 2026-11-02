"""AI Agent ultra 0009.
Multi-tier local decision and adaptation.
"""
from __future__ import annotations

ID = "agent_ultra_0009"

def describe() -> dict:
    return {"id": ID, "kind": "agent", "tier": 9 % 7, "local": True, "ultra": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    if health < 0.25:
        action = "retreat"
    elif threat > 0.65:
        action = "engage"
    else:
        action = "observe"
    return {"ok": True, "id": ID, "action": action, "confidence": 0.75 + (9 % 20) * 0.01}

def adapt(feedback: str = "") -> dict:
    if not feedback:
        return {"ok": False, "reason": "no_feedback"}
    return {"ok": True, "id": ID, "updated": True, "note": feedback[:80]}
