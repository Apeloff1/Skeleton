"""More scattered Ai_M 3432.
"""
from __future__ import annotations

ID = "ai_m_more_3432"

def describe() -> dict:
    return {"id": ID, "kind": "ai_m", "scattered": True, "more": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.79 + (3432 % 14) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "more_op", "size": len(payload or {})}
