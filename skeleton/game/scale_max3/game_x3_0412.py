"""Max scattered Game_X3 0412.
"""
from __future__ import annotations

ID = "game_x3_max3_0412"

def describe() -> dict:
    return {"id": ID, "kind": "game_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (412 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
