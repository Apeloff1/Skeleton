"""Pet peak 0100.
"""
from __future__ import annotations

ID = "pet_peak_0100"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 100}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
