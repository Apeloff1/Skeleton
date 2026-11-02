"""Emote eco_peak 0306.
"""
from __future__ import annotations

ID = "emote_eco_peak_0306"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 306}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
