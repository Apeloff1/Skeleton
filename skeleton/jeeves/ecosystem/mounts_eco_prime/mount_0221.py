"""Mount eco_prime 0221.
"""
from __future__ import annotations

ID = "mount_eco_prime_0221"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 221}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
