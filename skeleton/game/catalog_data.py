"""data/catalog tables for NEXUS-EXTRACT. Flavor stays in tables. Cards stay prose-zero."""

from __future__ import annotations

import hashlib
from typing import Any

from skeleton.game.encounters import pack_tables
from skeleton.game.provenance import meta


ITEMS = (
    ("item_scrap_coil", "scrap", 2, "coil"),
    ("item_heat_sink", "parts", 3, "sink"),
    ("item_extract_key", "key", 1, "key"),
    ("item_dream_cap", "parts", 4, "cap"),
    ("item_stalker_bait", "scrap", 1, "bait"),
    ("item_forge_blank", "parts", 5, "blank"),
    ("item_route_flare", "scrap", 2, "flare"),
    ("item_sleep_tab", "parts", 2, "tab"),
)
QUESTS = (
    ("q_first_heat", "heat", 8),
    ("q_first_extract", "extract", 1),
    ("q_dream_once", "dream", 1),
    ("q_craft_sink", "craft", 1),
    ("q_seal_door", "route", 1),
    ("q_bait_stalker", "ai", 1),
)


class CatalogDataError(ValueError):
    """Catalog data contract violation."""


def _digest(label: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{label}:cat".encode("utf-8")).hexdigest()


def items(seed: int) -> dict[str, Any]:
    rows = []
    for index, (item_id, kind, cost, rotor) in enumerate(ITEMS):
        rows.append({
            "id": item_id,
            "kind": kind,
            "cost": cost,
            "rotor": rotor,
            "digest": _digest(item_id, seed),
            "index": index,
            "stored_prose": 0,
        })
    return {
        "kind": "catalog_items",
        "path": "data/catalog/items.json",
        "meta": meta(path="data/catalog/items.json", seed=seed, step="mass_forge", rotor="items"),
        "n": len(rows),
        "rows": rows,
        "stored_prose": 0,
    }


def quests(seed: int) -> dict[str, Any]:
    rows = []
    for index, (quest_id, verb, count) in enumerate(QUESTS):
        rows.append({
            "id": quest_id,
            "verb": verb,
            "count": count,
            "digest": _digest(quest_id, seed),
            "index": index,
            "stored_prose": 0,
        })
    return {
        "kind": "catalog_quests",
        "path": "data/catalog/quests.json",
        "meta": meta(path="data/catalog/quests.json", seed=seed, step="mass_forge", rotor="quests"),
        "n": len(rows),
        "rows": rows,
        "stored_prose": 0,
    }


def pack(seed: int) -> dict[str, Any]:
    tables = pack_tables(seed)
    bag = items(seed)
    book = quests(seed)
    return {
        "kind": "catalog_data",
        "seed": int(seed),
        "items": bag,
        "quests": book,
        "encounters": tables,
        "n": bag["n"] + book["n"] + tables["n"],
        "paths": [bag["path"], book["path"], "data/catalog/encounters.json", "data/catalog/hazards.json", "data/catalog/routes.json"],
        "stored_prose": 0,
    }
