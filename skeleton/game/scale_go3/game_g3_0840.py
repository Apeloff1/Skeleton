"""Go scattered Game_G3 0840.
"""
from __future__ import annotations

ID = "game_g3_go3_0840"

def describe() -> dict:
    return {"id": ID, "kind": "game_g3", "scattered": True, "go": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.83 + (840 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "go3_op", "size": len(payload or {})}
