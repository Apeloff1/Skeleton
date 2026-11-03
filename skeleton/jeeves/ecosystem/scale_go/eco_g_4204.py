"""Go scattered Eco_G 4204.
"""
from __future__ import annotations

ID = "eco_g_go_4204"

def describe() -> dict:
    return {"id": ID, "kind": "eco_g", "scattered": True, "go": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.81 + (4204 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "go_op", "size": len(payload or {})}
