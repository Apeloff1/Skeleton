from __future__ import annotations

import json

from skeleton.game.catalog_gen import N, table
from skeleton.game.catalog_index import MODULES, census
from skeleton.game.catalog_items_table import by_id, size


def test_census_is_large_and_prose_zero() -> None:
    card = census()
    assert card["modules"] == len(MODULES)
    assert card["n"] >= 18000
    assert card["stored_prose"] == 0
    assert card["sota_ready"] is False
    assert all(row["n"] > 0 for row in card["tables"])


def test_item_lookup_stable() -> None:
    assert size() >= 900
    row = by_id("item_0000")
    assert row["p"] == 0 or row.get("stored_prose") == 0
    assert row["id"] == "item_0000"
    assert table("catalog_items_table", 8)[0]["id"] == "item_0000"
    assert N == 1000


def test_cli_catalog(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["catalog"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["n"] >= 18000
    assert payload["sota_ready"] is False
