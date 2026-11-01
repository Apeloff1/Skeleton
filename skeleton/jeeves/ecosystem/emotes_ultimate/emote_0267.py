"""Emote ultimate 0267.
"""
from __future__ import annotations

ID = "emote_ultimate_0267"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 267}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
