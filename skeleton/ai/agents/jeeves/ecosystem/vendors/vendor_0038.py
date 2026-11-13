"""Vendor 0038.
"""
from __future__ import annotations

VENDOR = "vendor_0038"

def stock() -> list[dict]:
    return [{"id": f"item_{38}_{k}", "price": 20 + k * 5} for k in range(4)]

def buy(item: str, gold: int) -> dict:
    if not item or gold < 0:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "vendor": VENDOR, "item": item, "spent": min(gold, 100)}
