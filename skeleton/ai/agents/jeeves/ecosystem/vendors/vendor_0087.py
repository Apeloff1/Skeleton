"""Vendor 0087.
"""
from __future__ import annotations

VENDOR = "vendor_0087"

def stock() -> list[dict]:
    return [{"id": f"item_{87}_{k}", "price": 20 + k * 5} for k in range(4)]

def buy(item: str, gold: int) -> dict:
    if not item or gold < 0:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "vendor": VENDOR, "item": item, "spent": min(gold, 100)}
