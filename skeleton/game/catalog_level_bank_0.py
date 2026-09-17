"""Level bank 0. 1000 rows via catalog_gen."""
from __future__ import annotations
from typing import Any
from skeleton.game.catalog_gen import table
KIND = "catalog_level_bank_0"
ROWS = table(KIND)
def rows() -> tuple[dict[str, Any], ...]:
    return ROWS
def size() -> int:
    return len(ROWS)
def by_id(item_id: str) -> dict[str, Any]:
    for row in ROWS:
        if row["id"] == item_id:
            return dict(row)
    raise KeyError(item_id)
def card() -> dict[str, Any]:
    return {"kind": KIND, "n": len(ROWS), "stored_prose": 0}
