"""Max scattered Eco_X3 3438.
"""
from __future__ import annotations

ID = "eco_x3_max3_3438"

def describe() -> dict:
    return {"id": ID, "kind": "eco_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (3438 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
