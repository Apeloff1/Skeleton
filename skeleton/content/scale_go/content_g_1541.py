"""Go scattered Content_G 1541.
"""
from __future__ import annotations

ID = "content_g_go_1541"

def describe() -> dict:
    return {"id": ID, "kind": "content_g", "scattered": True, "go": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.81 + (1541 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "go_op", "size": len(payload or {})}
