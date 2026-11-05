"""Deterministic local discovery is bounded, source-aware and unprivileged."""
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError
from skeleton.ai.game_builder.studio_ecosystem_search import search_blueprints


def test_fast_genre_discovery_order_and_biome_filter():
    result = search_blueprints("arena_fighting", limit=100)
    assert result["matched_projects"] == 16
    assert result["returned_projects"] == 16
    assert result["results"] == sorted(result["results"],
                                        key=lambda x: (-x["score"], x["id"]))
    assert result["release_certified"] is False
    narrow = search_blueprints("arena_fighting", biome="glacial_fjord")
    assert [r["id"] for r in narrow["results"]] == ["studio_arena_fighting_glacial_fjord"]


def test_deep_finds_provenance_bound_narrative_without_provider():
    fast = search_blueprints("illegal match-rigging cartel")
    deep = search_blueprints("illegal match-rigging cartel", deep=True, limit=20)
    assert fast["matched_projects"] == 0
    assert deep["matched_projects"] == 16
    assert all("quest" in row["matched_sections"] or "narrative" in row["matched_sections"]
               for row in deep["results"])
    assert deep["truncated_to_limit"] is False


@pytest.mark.parametrize("query", ["", " ", "a\nb", "a"*257, "!"*10])
def test_query_rejection(query):
    with pytest.raises(StudioEcosystemError):
        search_blueprints(query)


def test_no_ambiguous_limits_or_filter_bypass():
    with pytest.raises(StudioEcosystemError):
        search_blueprints("arena", limit=True)
    with pytest.raises(StudioEcosystemError):
        search_blueprints("arena", deep="yes")
    with pytest.raises(StudioEcosystemError):
        search_blueprints("arena", genre="../../secret")
    with pytest.raises(StudioEcosystemError):
        search_blueprints("arena", biome="glacial_fjord", limit=0)
