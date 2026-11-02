"""Emote eco_supreme 0250.
"""
from __future__ import annotations

ID = "emote_eco_supreme_0250"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 250}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
