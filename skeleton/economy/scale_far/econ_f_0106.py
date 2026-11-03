"""Far scattered Econ_F 0106.
"""
from __future__ import annotations

ID = "econ_f_far_0106"

def describe() -> dict:
    return {"id": ID, "kind": "econ_f", "scattered": True, "far": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.78 + (106 % 16) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "far_op", "size": len(payload or {})}
