"""Source diversity and rights-review census over accepted raw discovery history."""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.game_builder.dragon_almanacs import read_source_registry
from skeleton.ai.game_builder.dragon_discovery_census import discovery_census
from skeleton.ai.game_builder.dragon_discovery_reconciled import (
    verify_reconciled_chain, SOURCE_BATCHES, EXCLUDED_ORPHANS,
)


CATALOG = (
    Path(__file__).resolve().parents[1] /
    "skeleton/ai/game_builder/catalogs/dragon_sources_20261010"
)


@pytest.fixture(scope="module")
def registry():
    return read_source_registry(CATALOG)


@pytest.fixture(scope="module")
def census(registry):
    return discovery_census(registry, top_hosts=30)


def test_source_census_counts_full_pinned_lineage_not_orphans(registry, census):
    verified = verify_reconciled_chain(registry)
    assert census["raw_url_leads"] == verified["raw_url_leads"] == 15175
    assert census["baseline_raw_leads"] == 4405
    assert census["supplement_raw_leads"] == 10770
    assert census["canonical_distinct_urls"] == verified[
        "canonical_candidate_sources"]
    assert census["raw_to_canonical_collisions"] == (
        15175 - census["canonical_distinct_urls"])
    assert len(SOURCE_BATCHES) == 16
    assert all(path not in SOURCE_BATCHES for path in EXCLUDED_ORPHANS)
    assert sum(census["category_counts_canonical"].values()) == census[
        "canonical_distinct_urls"]


def test_census_exposes_host_concentration_not_independence(census):
    assert census["unique_hosts"] > 100
    assert len(census["top_hosts"]) == 30
    assert census["host_diversity_not_source_independence"] is True
    assert all(hit["canonical_urls"] <= hit["raw_leads"]
               for hit in census["top_hosts"])
    assert sum(hit["percent_of_canonical_urls"] for hit in census["top_hosts"]
               ) <= 100.1
    assert all(item["independently_corroborated"] is False
               for item in census["catalog_link_contributions"])
    assert sum(census["rights_review_keyword_hits_raw"].values()) >= 0


def test_neither_metadata_census_nor_keyword_detection_grants_rights(census):
    assert census["source_of_truth"] == "frozen_reconciled_discovery_chain"
    assert census["rights_keyword_hit_not_legal_finding"] is True
    assert census["verified_document_identity_not_link_content"] is True
    assert all(census[field] is False for field in (
        "crawler_authorized", "source_rights_approved",
        "training_authorized", "memory_promotion_authorized",
    ))


def test_census_limits_host_reporting_and_fails_closed(registry):
    for invalid in (0, True, 101, "25", -1):
        with pytest.raises(ValueError, match="top host"):
            discovery_census(registry, top_hosts=invalid)


def test_incomplete_source_lineage_is_never_reported_as_fresh(registry, monkeypatch):
    import skeleton.ai.game_builder.dragon_discovery_census as module
    from skeleton.ai.game_builder.dragon_discovery_reconciled import _chain
    existing = _chain()
    monkeypatch.setattr(module, "_chain", lambda: existing[:-1])
    with pytest.raises(ValueError):
        module.discovery_census(registry)
