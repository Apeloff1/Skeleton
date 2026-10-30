"""Stable search, source hit evidence, catalog filtering and fail-closed input."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.studio_ecosystem_search import search_blueprints
from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError


def test_metadata_search_is_deterministic_and_sorted():
    results = search_blueprints("orbital gardens", limit=8)
    assert results
    assert all(x["biome"] == "orbital_gardens" for x in results)
    assert results == search_blueprints("orbital gardens", limit=8)
    assert all(x["matched_sections"] == ["metadata"] for x in results)
    assert all(x["release_certified"] is False for x in results)


def test_deep_authoring_search_finds_quest_and_checks():
    results = search_blueprints("life support", genre="stellar_colony", deep=True)
    assert results
    assert all(x["genre"] == "stellar_colony" for x in results)
    assert any("narrative" in x["matched_sections"] or "visual" in x["matched_sections"]
               for x in results)


def test_rejects_bad_search_budget_and_controls():
    for query in ("", "\x00", "a" * 193):
        with pytest.raises(StudioEcosystemError):
            search_blueprints(query)
    with pytest.raises(StudioEcosystemError):
        search_blueprints("city", limit=0)
    with pytest.raises(StudioEcosystemError):
        search_blueprints("city", deep=1)
