"""AI Agent core 1391.
Multi-tier local decision and adaptation.
"""
from __future__ import annotations

ID = "agent_core_1391"

def describe() -> dict:
    return {"id": ID, "kind": "agent", "tier": 1391 % 7, "local": True}

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
    return {"ok": True, "id": ID, "action": action, "confidence": 0.72 + (1391 % 20) * 0.01}

def adapt(feedback: str = "") -> dict:
    if not feedback:
        return {"ok": False, "reason": "no_feedback"}
    return {"ok": True, "id": ID, "updated": True, "note": feedback[:80]}
