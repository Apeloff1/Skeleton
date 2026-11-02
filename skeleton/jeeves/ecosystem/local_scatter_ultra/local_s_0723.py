"""Scattered Local_S 0723.
"""
from __future__ import annotations

ID = "local_s_scatter3_0723"

def describe() -> dict:
    return {"id": ID, "kind": "local_s", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
