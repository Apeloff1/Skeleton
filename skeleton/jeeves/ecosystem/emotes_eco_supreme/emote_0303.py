"""Emote eco_supreme 0303.
"""
from __future__ import annotations

ID = "emote_eco_supreme_0303"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 303}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
