"""Emote eco_apex 0271.
"""
from __future__ import annotations

ID = "emote_eco_apex_0271"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 271}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
