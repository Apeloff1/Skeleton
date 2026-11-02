"""Scattered Organ 0364.
"""
from __future__ import annotations

ID = "organ_scatter3_0364"

def describe() -> dict:
    return {"id": ID, "kind": "organ", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
