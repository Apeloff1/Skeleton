"""Emote prime 0102.
"""
from __future__ import annotations

ID = "emote_prime_0102"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 102}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
