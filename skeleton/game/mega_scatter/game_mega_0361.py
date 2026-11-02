"""Mega scattered Game_Mega 0361.
"""
from __future__ import annotations

ID = "game_mega_mega_0361"

def describe() -> dict:
    return {"id": ID, "kind": "game_mega", "scattered": True, "mega": True}

def reason(context: dict | None = None) -> dict:
    ctx = context or {}
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.78 + (361 % 12) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "mega_op", "size": len(payload or {})}
