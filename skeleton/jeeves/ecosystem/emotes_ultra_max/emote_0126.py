"""Emote ultra_max 0126.
"""
from __future__ import annotations

ID = "emote_ultra_max_0126"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 126}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
