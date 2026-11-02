"""Ach eco_prime 0237.
"""
from __future__ import annotations

ID = "ach_eco_prime_0237"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 237}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
