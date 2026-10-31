"""Emote prime 0120.
"""
from __future__ import annotations

ID = "emote_prime_0120"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 120}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
