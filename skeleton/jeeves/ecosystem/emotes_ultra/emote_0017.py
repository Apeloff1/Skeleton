"""Emote ultra 0017.
"""
from __future__ import annotations

ID = "emote_ultra_0017"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 17}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
