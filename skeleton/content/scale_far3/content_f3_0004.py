"""Far scattered Content_F3 0004.
"""
from __future__ import annotations

ID = "content_f3_far3_0004"

def describe() -> dict:
    return {"id": ID, "kind": "content_f3", "scattered": True, "far": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.80 + (4 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "far3_op", "size": len(payload or {})}
