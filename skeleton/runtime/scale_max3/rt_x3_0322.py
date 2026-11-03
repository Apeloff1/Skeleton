"""Max scattered Rt_X3 0322.
"""
from __future__ import annotations

ID = "rt_x3_max3_0322"

def describe() -> dict:
    return {"id": ID, "kind": "rt_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (322 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
