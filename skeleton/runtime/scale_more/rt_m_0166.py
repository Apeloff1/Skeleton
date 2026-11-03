"""More scattered Rt_M 0166.
"""
from __future__ import annotations

ID = "rt_m_more_0166"

def describe() -> dict:
    return {"id": ID, "kind": "rt_m", "scattered": True, "more": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.79 + (166 % 14) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "more_op", "size": len(payload or {})}
