"""Scattered Phys 0268.
"""
from __future__ import annotations

ID = "phys_scatter3_0268"

def describe() -> dict:
    return {"id": ID, "kind": "phys", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
