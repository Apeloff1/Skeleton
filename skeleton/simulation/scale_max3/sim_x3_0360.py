"""Max scattered Sim_X3 0360.
"""
from __future__ import annotations

ID = "sim_x3_max3_0360"

def describe() -> dict:
    return {"id": ID, "kind": "sim_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (360 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
