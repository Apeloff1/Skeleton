"""Emote eco_apex 0387.
"""
from __future__ import annotations

ID = "emote_eco_apex_0387"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 387}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
