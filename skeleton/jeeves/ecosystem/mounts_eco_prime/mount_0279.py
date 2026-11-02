"""Mount eco_prime 0279.
"""
from __future__ import annotations

ID = "mount_eco_prime_0279"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 279}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
