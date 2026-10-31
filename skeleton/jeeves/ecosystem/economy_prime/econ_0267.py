"""Econ prime 0267.
"""
from __future__ import annotations

ID = "econ_prime_0267"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 267}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
