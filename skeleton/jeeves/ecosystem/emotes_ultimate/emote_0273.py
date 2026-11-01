"""Emote ultimate 0273.
"""
from __future__ import annotations

ID = "emote_ultimate_0273"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 273}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
