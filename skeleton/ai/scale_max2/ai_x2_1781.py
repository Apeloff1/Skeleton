"""Max scattered Ai_X2 1781.
"""
from __future__ import annotations

ID = "ai_x2_max2_1781"

def describe() -> dict:
    return {"id": ID, "kind": "ai_x2", "scattered": True, "max": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.76 + (1781 % 14) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
