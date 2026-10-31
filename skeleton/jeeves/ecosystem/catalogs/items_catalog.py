"""Catalog: items.
"""
from __future__ import annotations

ITEMS = [
    {"id": f"items_0", "rarity": "common"},
    {"id": f"items_1", "rarity": "rare"},
    {"id": f"items_2", "rarity": "epic"},
]

def get(item_id: str) -> dict | None:
    for item in ITEMS:
        if item["id"] == item_id:
            return item
    return None

def all_ids() -> list[str]:
    return [i["id"] for i in ITEMS]
