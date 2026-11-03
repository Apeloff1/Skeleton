"""Far scattered Local_F3 0657.
"""
from __future__ import annotations

ID = "local_f3_far3_0657"

def describe() -> dict:
    return {"id": ID, "kind": "local_f3", "scattered": True, "far": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.80 + (657 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "far3_op", "size": len(payload or {})}
