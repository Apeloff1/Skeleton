"""Emote eco_supreme 0117.
"""
from __future__ import annotations

ID = "emote_eco_supreme_0117"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 117}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
