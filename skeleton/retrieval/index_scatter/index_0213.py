"""Scattered Index 0213.
"""
from __future__ import annotations

ID = "index_scatter3_0213"

def describe() -> dict:
    return {"id": ID, "kind": "index", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
