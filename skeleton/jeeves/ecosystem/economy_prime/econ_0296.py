"""Econ prime 0296.
"""
from __future__ import annotations

ID = "econ_prime_0296"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 296}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
