"""Emote peak 0096.
"""
from __future__ import annotations

ID = "emote_peak_0096"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 96}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
