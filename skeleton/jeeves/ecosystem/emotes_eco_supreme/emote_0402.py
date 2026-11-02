"""Emote eco_supreme 0402.
"""
from __future__ import annotations

ID = "emote_eco_supreme_0402"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 402}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
