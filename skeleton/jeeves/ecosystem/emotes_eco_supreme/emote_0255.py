"""Emote eco_supreme 0255.
"""
from __future__ import annotations

ID = "emote_eco_supreme_0255"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 255}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
