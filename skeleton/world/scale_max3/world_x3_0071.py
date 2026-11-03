"""Max scattered World_X3 0071.
"""
from __future__ import annotations

ID = "world_x3_max3_0071"

def describe() -> dict:
    return {"id": ID, "kind": "world_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (71 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
