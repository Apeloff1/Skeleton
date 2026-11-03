"""Go scattered Econ_G 0038.
"""
from __future__ import annotations

ID = "econ_g_go_0038"

def describe() -> dict:
    return {"id": ID, "kind": "econ_g", "scattered": True, "go": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.81 + (38 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "go_op", "size": len(payload or {})}
