"""Emote supreme 0172.
"""
from __future__ import annotations

ID = "emote_supreme_0172"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 172}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
