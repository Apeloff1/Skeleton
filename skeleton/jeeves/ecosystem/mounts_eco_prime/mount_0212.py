"""Mount eco_prime 0212.
"""
from __future__ import annotations

ID = "mount_eco_prime_0212"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 212}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
