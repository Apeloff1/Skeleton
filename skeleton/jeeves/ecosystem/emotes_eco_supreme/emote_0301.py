"""Emote eco_supreme 0301.
"""
from __future__ import annotations

ID = "emote_eco_supreme_0301"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 301}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
