"""Far scattered Game_F3 0738.
"""
from __future__ import annotations

ID = "game_f3_far3_0738"

def describe() -> dict:
    return {"id": ID, "kind": "game_f3", "scattered": True, "far": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.80 + (738 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "far3_op", "size": len(payload or {})}
