"""Scattered Sota 0293.
"""
from __future__ import annotations

ID = "sota_scatter3_0293"

def describe() -> dict:
    return {"id": ID, "kind": "sota", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
