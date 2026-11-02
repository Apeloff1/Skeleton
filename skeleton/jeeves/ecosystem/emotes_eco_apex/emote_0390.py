"""Emote eco_apex 0390.
"""
from __future__ import annotations

ID = "emote_eco_apex_0390"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 390}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
