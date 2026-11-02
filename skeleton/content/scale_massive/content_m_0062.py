"""Massive scattered Content_M 0062.
"""
from __future__ import annotations

ID = "content_m_massive_0062"

def describe() -> dict:
    return {"id": ID, "kind": "content_m", "scattered": True, "massive": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.77 + (62 % 18) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "massive_op", "size": len(payload or {})}
