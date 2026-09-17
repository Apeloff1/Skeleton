"""Census for the large SOTA catalogs. Lazy import. stored_prose=0."""

from __future__ import annotations

from importlib import import_module
from typing import Any


MODULES = (
    "skeleton.game.catalog_ai_table",
    "skeleton.game.catalog_balance_table",
    "skeleton.game.catalog_doors_table",
    "skeleton.game.catalog_encounters_table",
    "skeleton.game.catalog_extracts_table",
    "skeleton.game.catalog_heat_table",
    "skeleton.game.catalog_items_table",
    "skeleton.game.catalog_mass_table",
    "skeleton.game.catalog_quests_table",
    "skeleton.game.catalog_recipes_table",
    "skeleton.game.catalog_replay_fix_table",
    "skeleton.game.catalog_rights_table",
    "skeleton.game.catalog_rooms_table",
    "skeleton.game.catalog_seeds_table",
    "skeleton.game.catalog_tokens_table",
    "skeleton.game.catalog_ticks_table",
    "skeleton.game.catalog_level_bank_0",
    "skeleton.game.catalog_level_bank_1",
    "skeleton.game.catalog_level_bank_2",
    "skeleton.game.catalog_level_bank_3",
    "skeleton.game.catalog_level_bank_4",
    "skeleton.game.catalog_level_bank_5",
    "skeleton.game.catalog_level_bank_6",
    "skeleton.game.catalog_level_bank_7",
)


class CatalogIndexError(ValueError):
    """Catalog index contract violation."""


def census() -> dict[str, Any]:
    tables = []
    total = 0
    for name in MODULES:
        mod = import_module(name)
        n = int(mod.size())
        if n < 1:
            raise CatalogIndexError(f"empty table {name}")
        card = mod.card()
        if card.get("stored_prose") != 0:
            raise CatalogIndexError("prose in catalog card")
        tables.append({"module": name, "kind": card["kind"], "n": n})
        total += n
    return {
        "kind": "catalog_index",
        "modules": len(tables),
        "n": total,
        "tables": tables,
        "sota_ready": False,
        "stored_prose": 0,
        "ok": True,
    }
