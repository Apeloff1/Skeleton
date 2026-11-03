"""Far scattered Deck_F 0260.
"""
from __future__ import annotations

ID = "deck_f_far2_0260"

def describe() -> dict:
    return {"id": ID, "kind": "deck_f", "scattered": True, "far": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.74 + (260 % 18) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
