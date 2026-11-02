"""Mount eco_prime 0239.
"""
from __future__ import annotations

ID = "mount_eco_prime_0239"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 239}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
