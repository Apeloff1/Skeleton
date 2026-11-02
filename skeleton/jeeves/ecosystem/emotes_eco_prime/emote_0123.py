"""Emote eco_prime 0123.
"""
from __future__ import annotations

ID = "emote_eco_prime_0123"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 123}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
