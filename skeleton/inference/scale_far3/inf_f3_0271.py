"""Far scattered Inf_F3 0271.
"""
from __future__ import annotations

ID = "inf_f3_far3_0271"

def describe() -> dict:
    return {"id": ID, "kind": "inf_f3", "scattered": True, "far": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.80 + (271 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "far3_op", "size": len(payload or {})}
