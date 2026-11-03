"""Max scattered Rt_X3 0619.
"""
from __future__ import annotations

ID = "rt_x3_max3_0619"

def describe() -> dict:
    return {"id": ID, "kind": "rt_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (619 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
