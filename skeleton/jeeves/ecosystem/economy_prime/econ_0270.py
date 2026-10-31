"""Econ prime 0270.
"""
from __future__ import annotations

ID = "econ_prime_0270"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 270}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
