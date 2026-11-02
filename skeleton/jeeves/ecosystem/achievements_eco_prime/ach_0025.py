"""Ach eco_prime 0025.
"""
from __future__ import annotations

ID = "ach_eco_prime_0025"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 25}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
