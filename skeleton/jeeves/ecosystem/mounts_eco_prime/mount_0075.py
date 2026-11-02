"""Mount eco_prime 0075.
"""
from __future__ import annotations

ID = "mount_eco_prime_0075"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 75}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
