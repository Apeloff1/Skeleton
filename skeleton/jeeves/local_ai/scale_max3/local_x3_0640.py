"""Max scattered Local_X3 0640.
"""
from __future__ import annotations

ID = "local_x3_max3_0640"

def describe() -> dict:
    return {"id": ID, "kind": "local_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (640 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
