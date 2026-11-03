"""Max scattered Core_X3 0134.
"""
from __future__ import annotations

ID = "core_x3_max3_0134"

def describe() -> dict:
    return {"id": ID, "kind": "core_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (134 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
