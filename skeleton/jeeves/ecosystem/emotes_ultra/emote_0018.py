"""Emote ultra 0018.
"""
from __future__ import annotations

ID = "emote_ultra_0018"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 18}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
