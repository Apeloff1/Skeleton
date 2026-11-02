"""Scattered AI Btree 0596.
"""
from __future__ import annotations

ID = "btree_scatter_0596"

def describe() -> dict:
    return {"id": ID, "kind": "btree", "scattered": True, "local": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.76 + (596 % 15) * 0.01}

def adapt(feedback: str = "") -> dict:
    return {"ok": bool(feedback), "id": ID, "updated": bool(feedback)}
