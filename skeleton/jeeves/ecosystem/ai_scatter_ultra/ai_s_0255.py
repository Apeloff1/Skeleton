"""Scattered Ai_S 0255.
"""
from __future__ import annotations

ID = "ai_s_scatter3_0255"

def describe() -> dict:
    return {"id": ID, "kind": "ai_s", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
