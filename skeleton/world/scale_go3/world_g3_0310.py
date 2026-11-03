"""Go scattered World_G3 0310.
"""
from __future__ import annotations

ID = "world_g3_go3_0310"

def describe() -> dict:
    return {"id": ID, "kind": "world_g3", "scattered": True, "go": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.83 + (310 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "go3_op", "size": len(payload or {})}
