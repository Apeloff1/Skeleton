"""Mount eco_peak 0187.
"""
from __future__ import annotations

ID = "mount_eco_peak_0187"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 187}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
