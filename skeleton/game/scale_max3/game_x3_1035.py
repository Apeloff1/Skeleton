"""Max scattered Game_X3 1035.
"""
from __future__ import annotations

ID = "game_x3_max3_1035"

def describe() -> dict:
    return {"id": ID, "kind": "game_x3", "scattered": True, "max": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.82 + (1035 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "max3_op", "size": len(payload or {})}
