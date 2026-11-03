"""Max scattered Eco_X2 0100.
"""
from __future__ import annotations

ID = "eco_x2_max2_0100"

def describe() -> dict:
    return {"id": ID, "kind": "eco_x2", "scattered": True, "max": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.76 + (100 % 14) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
