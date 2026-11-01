"""Econ supreme 0380.
"""
from __future__ import annotations

ID = "econ_supreme_0380"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 380}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
