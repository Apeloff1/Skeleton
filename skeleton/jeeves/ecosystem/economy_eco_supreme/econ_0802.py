"""Econ eco_supreme 0802.
"""
from __future__ import annotations

ID = "econ_eco_supreme_0802"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 802}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
