"""Max scattered Deck_X 0130.
"""
from __future__ import annotations

ID = "deck_x_max2_0130"

def describe() -> dict:
    return {"id": ID, "kind": "deck_x", "scattered": True, "max": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.76 + (130 % 14) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
