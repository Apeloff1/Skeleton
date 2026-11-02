"""Scattered Cortex 0300.
"""
from __future__ import annotations

ID = "cortex_scatter3_0300"

def describe() -> dict:
    return {"id": ID, "kind": "cortex", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
