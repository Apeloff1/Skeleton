"""Emote ultra_max 0189.
"""
from __future__ import annotations

ID = "emote_ultra_max_0189"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 189}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
