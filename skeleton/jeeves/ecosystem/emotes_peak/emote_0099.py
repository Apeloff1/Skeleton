"""Emote peak 0099.
"""
from __future__ import annotations

ID = "emote_peak_0099"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
