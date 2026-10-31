"""Pet 0029.
"""
from __future__ import annotations

PET = "pet_0029"

def follow(owner: str) -> dict:
    if not owner:
        return {"ok": False, "reason": "no_owner"}
    return {"ok": True, "pet": PET, "owner": owner, "loyalty": 0.8}
