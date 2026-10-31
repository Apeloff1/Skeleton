"""Catalog: enemies.
"""
from __future__ import annotations

ITEMS = [
    {"id": f"enemies_0", "rarity": "common"},
    {"id": f"enemies_1", "rarity": "rare"},
    {"id": f"enemies_2", "rarity": "epic"},
]

def get(item_id: str) -> dict | None:
    for item in ITEMS:
        if item["id"] == item_id:
            return item
    return None

def all_ids() -> list[str]:
    return [i["id"] for i in ITEMS]
