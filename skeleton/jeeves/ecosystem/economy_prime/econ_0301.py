"""Econ prime 0301.
"""
from __future__ import annotations

ID = "econ_prime_0301"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 301}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
