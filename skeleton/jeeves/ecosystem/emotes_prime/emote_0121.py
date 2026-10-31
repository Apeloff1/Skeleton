"""Emote prime 0121.
"""
from __future__ import annotations

ID = "emote_prime_0121"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 121}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
