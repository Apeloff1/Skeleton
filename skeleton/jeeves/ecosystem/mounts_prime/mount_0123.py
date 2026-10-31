"""Mount prime 0123.
"""
from __future__ import annotations

ID = "mount_prime_0123"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 123}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
