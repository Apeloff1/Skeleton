"""Ach prime 0241.
"""
from __future__ import annotations

ID = "ach_prime_0241"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 241}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
