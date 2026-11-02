"""Scattered Era_Sim 0013.
"""
from __future__ import annotations

ID = "era_sim_scatter3_0013"

def describe() -> dict:
    return {"id": ID, "kind": "era_sim", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
