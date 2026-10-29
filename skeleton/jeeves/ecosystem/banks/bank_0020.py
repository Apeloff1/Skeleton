"""Bank 0020.
"""
from __future__ import annotations

BANK = "bank_0020"

def deposit(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "bank": BANK, "stored": item}

def withdraw(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "bank": BANK, "retrieved": item}
