"""Far scattered Sim_F3 0405.
"""
from __future__ import annotations

ID = "sim_f3_far3_0405"

def describe() -> dict:
    return {"id": ID, "kind": "sim_f3", "scattered": True, "far": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.80 + (405 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "far3_op", "size": len(payload or {})}
