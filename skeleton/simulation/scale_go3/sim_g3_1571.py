"""Go scattered Sim_G3 1571.
"""
from __future__ import annotations

ID = "sim_g3_go3_1571"

def describe() -> dict:
    return {"id": ID, "kind": "sim_g3", "scattered": True, "go": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.83 + (1571 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "go3_op", "size": len(payload or {})}
