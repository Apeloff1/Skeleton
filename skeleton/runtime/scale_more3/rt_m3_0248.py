"""More scattered Rt_M3 0248.
"""
from __future__ import annotations

ID = "rt_m3_more3_0248"

def describe() -> dict:
    return {"id": ID, "kind": "rt_m3", "scattered": True, "more": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.81 + (248 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "more3_op", "size": len(payload or {})}
