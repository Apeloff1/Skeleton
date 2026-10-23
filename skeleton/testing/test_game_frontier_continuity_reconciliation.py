"""Regression coverage for additive continuity reconciliation.

The original epoch/saga/epic index positions remain stable; continuity is a
separate virtual namespace rather than a destructive replacement for Epic.
"""
from __future__ import annotations

import pytest

from skeleton.forge.game_frontier_studio_authoring import AUTHORING_ACTIONS
from skeleton.forge.game_frontier_studio_continuity_production import (
    CONTINUITY_ACTIONS, CONTINUITIES, describe_continuity, search_continuities,
)
from skeleton.forge.game_frontier_studio_continuity_handbooks import list_books
from skeleton.forge.game_frontier_studio import StudioError


def test_existing_authoring_indices_are_preserved():
    assert len(AUTHORING_ACTIONS) == 50_000_000_000_000
    assert len(CONTINUITY_ACTIONS) == 4_500_000_000_000
    assert len(set(CONTINUITIES)) == 10
    assert AUTHORING_ACTIONS[-1].startswith("epic_")


def test_continuity_index_is_bijective_and_source_backed():
    for index in (0, 1, 9, 10, 450_000, len(CONTINUITY_ACTIONS) - 1):
        operation = CONTINUITY_ACTIONS[index]
        assert operation in CONTINUITY_ACTIONS
        detail = describe_continuity(operation)
        assert detail["operation"] == operation
        assert detail["continuity"] in CONTINUITIES
        assert detail["actual_project_mutation"] is True
    assert "continuity_unregistered" not in CONTINUITY_ACTIONS


def test_continuity_paging_and_filters_are_bounded():
    output = search_continuities(continuity=CONTINUITIES[0], offset=0, limit=3)
    assert output["schema"] == "skeleton.forge.production_recipe_search.v1"
    assert output["total_catalog"] == 4_500_000_000_000
    assert len(output["items"]) == 3
    assert all(item["continuity"] == CONTINUITIES[0] for item in output["items"])
    with pytest.raises(StudioError):
        search_continuities(limit=65)
    with pytest.raises(StudioError):
        search_continuities(continuity="unregistered")


def test_bounded_virtual_handbook_discovery():
    results = list_books(offset=0, limit=2)
    assert results["matched"] > 0
    assert len(results["items"]) == 2
    with pytest.raises(StudioError):
        list_books(limit=65)
