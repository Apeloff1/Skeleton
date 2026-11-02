"""Mount eco_prime 0304.
"""
from __future__ import annotations

ID = "mount_eco_prime_0304"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 304}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
