"""Asset bank 0171.
"""
from __future__ import annotations

BANK = "asset_bank_0171"

def catalog() -> list[str]:
    return [f"asset_{n}" for n in range(4 + (171 % 6))]

def fetch(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "bank": BANK, "item": item, "fidelity": 0.93}
