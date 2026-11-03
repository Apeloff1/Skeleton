"""Far scattered World_F3 0201.
"""
from __future__ import annotations

ID = "world_f3_far3_0201"

def describe() -> dict:
    return {"id": ID, "kind": "world_f3", "scattered": True, "far": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.80 + (201 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "far3_op", "size": len(payload or {})}
