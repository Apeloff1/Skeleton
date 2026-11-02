"""Scattered Job 0141.
"""
from __future__ import annotations

ID = "job_scatter3_0141"

def describe() -> dict:
    return {"id": ID, "kind": "job", "scattered": True, "ultra": True}

def operate(payload: dict | None = None) -> dict:
    p = payload or {}
    return {"ok": True, "id": ID, "result": "scattered_op", "size": len(p)}
