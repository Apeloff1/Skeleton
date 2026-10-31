"""Emote ultra 0028.
"""
from __future__ import annotations

ID = "emote_ultra_0028"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 28}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
