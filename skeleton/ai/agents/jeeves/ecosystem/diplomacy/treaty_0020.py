"""Treaty 0020.
"""
from __future__ import annotations

TREATY = "treaty_0020"

def sign(a: str, b: str) -> dict:
    if not a or not b:
        return {"ok": False, "reason": "missing_party"}
    return {"ok": True, "treaty": TREATY, "parties": [a, b], "status": "active"}
