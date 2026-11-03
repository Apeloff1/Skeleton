"""Far scattered Core_F3 0123.
"""
from __future__ import annotations

ID = "core_f3_far3_0123"

def describe() -> dict:
    return {"id": ID, "kind": "core_f3", "scattered": True, "far": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.80 + (123 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "far3_op", "size": len(payload or {})}
