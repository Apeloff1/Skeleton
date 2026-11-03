"""More scattered Content_M 1042.
"""
from __future__ import annotations

ID = "content_m_more_1042"

def describe() -> dict:
    return {"id": ID, "kind": "content_m", "scattered": True, "more": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.79 + (1042 % 14) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "more_op", "size": len(payload or {})}
