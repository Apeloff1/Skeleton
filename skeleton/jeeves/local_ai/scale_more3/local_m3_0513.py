"""More scattered Local_M3 0513.
"""
from __future__ import annotations

ID = "local_m3_more3_0513"

def describe() -> dict:
    return {"id": ID, "kind": "local_m3", "scattered": True, "more": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.81 + (513 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "more3_op", "size": len(payload or {})}
