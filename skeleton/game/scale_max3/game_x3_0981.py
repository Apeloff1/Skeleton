"""Max scattered Game_X3 0981.
"""
from __future__ import annotations

ID = "game_x3_max3_0981"

def describe() -> dict:
    return {"id": ID, "kind": "game_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (981 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
