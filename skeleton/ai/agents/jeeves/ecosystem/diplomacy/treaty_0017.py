"""Treaty 0017.
"""
from __future__ import annotations

TREATY = "treaty_0017"

def sign(a: str, b: str) -> dict:
    if not a or not b:
        return {"ok": False, "reason": "missing_party"}
    return {"ok": True, "treaty": TREATY, "parties": [a, b], "status": "active"}
