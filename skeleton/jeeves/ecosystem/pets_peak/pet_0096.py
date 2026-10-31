"""Pet peak 0096.
"""
from __future__ import annotations

ID = "pet_peak_0096"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 96}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
