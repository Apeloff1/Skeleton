"""Scattered P5 0057.
"""
from __future__ import annotations

ID = "p5_scatter3_0057"

def describe() -> dict:
    return {"id": ID, "kind": "p5", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
