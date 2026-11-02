"""Emote eco_peak 0276.
"""
from __future__ import annotations

ID = "emote_eco_peak_0276"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 276}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
