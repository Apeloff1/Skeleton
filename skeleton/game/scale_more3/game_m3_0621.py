"""More scattered Game_M3 0621.
"""
from __future__ import annotations

ID = "game_m3_more3_0621"

def describe() -> dict:
    return {"id": ID, "kind": "game_m3", "scattered": True, "more": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.81 + (621 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "more3_op", "size": len(payload or {})}
