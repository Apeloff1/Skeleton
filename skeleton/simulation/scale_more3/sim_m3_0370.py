"""More scattered Sim_M3 0370.
"""
from __future__ import annotations

ID = "sim_m3_more3_0370"

def describe() -> dict:
    return {"id": ID, "kind": "sim_m3", "scattered": True, "more": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.81 + (370 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "more3_op", "size": len(payload or {})}
