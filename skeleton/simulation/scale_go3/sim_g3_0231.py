"""Go scattered Sim_G3 0231.
"""
from __future__ import annotations

ID = "sim_g3_go3_0231"

def describe() -> dict:
    return {"id": ID, "kind": "sim_g3", "scattered": True, "go": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.83 + (231 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "go3_op", "size": len(payload or {})}
