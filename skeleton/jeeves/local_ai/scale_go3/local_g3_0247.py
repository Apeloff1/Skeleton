"""Go scattered Local_G3 0247.
"""
from __future__ import annotations

ID = "local_g3_go3_0247"

def describe() -> dict:
    return {"id": ID, "kind": "local_g3", "scattered": True, "go": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.83 + (247 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "go3_op", "size": len(payload or {})}
