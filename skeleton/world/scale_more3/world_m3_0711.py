"""More scattered World_M3 0711.
"""
from __future__ import annotations

ID = "world_m3_more3_0711"

def describe() -> dict:
    return {"id": ID, "kind": "world_m3", "scattered": True, "more": True}

def reason(context: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "action": "process", "confidence": 0.81 + (711 % 10) * 0.01}

def operate(payload: dict | None = None) -> dict:
    return {"ok": True, "id": ID, "result": "more3_op", "size": len(payload or {})}
