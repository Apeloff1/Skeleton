"""Econ eco_prime 0703.
"""
from __future__ import annotations

ID = "econ_eco_prime_0703"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 703}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
