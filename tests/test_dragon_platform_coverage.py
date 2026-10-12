"""Hardware/era discovery coverage remains an auditable, non-authorizing signal."""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.game_builder.dragon_almanacs import read_source_registry
from skeleton.ai.game_builder.dragon_platform_coverage import (
    PLATFORM_ALIASES, _matches, _tokens, platform_discovery_matrix,
)

REGISTRY = (Path(__file__).resolve().parents[1] /
            "skeleton/ai/game_builder/catalogs/dragon_sources_20261010")


@pytest.fixture(scope="module")
def coverage():
    return platform_discovery_matrix(read_source_registry(REGISTRY),
                                     samples_per_platform=2)


def test_platform_aliases_are_distinct_bounded_and_word_boundary_aware():
    assert len(PLATFORM_ALIASES) >= 35
    assert len({key for key, _, _ in PLATFORM_ALIASES}) == len(PLATFORM_ALIASES)
    for key, group, aliases in PLATFORM_ALIASES:
        assert key and group
        assert aliases and len(set(aliases)) == len(aliases)
        assert all(isinstance(alias, str) and len(alias) >= 3 for alias in aliases)
    assert _matches(_tokens("An original Game Boy homebrew platformer"),
                    ("game boy",))
    assert not _matches(_tokens("game boycott"), ("game boy",))
    assert not _matches(_tokens("play style tool"), ("playstation 1",))
    assert _matches(_tokens("N64Dev libdragon SDK"), ("n64dev",))


def test_full_reconciled_platform_inventory_has_canonical_denominator(coverage):
    assert coverage["raw_link_leads"] == 15175
    assert coverage["canonical_distinct_urls_global"] > 4405
    assert coverage["canonical_distinct_urls_global"] <= 15175
    assert coverage["platforms_in_heuristic_catalog"] == len(PLATFORM_ALIASES)
    assert len(coverage["platforms"]) == len(PLATFORM_ALIASES)
    assert 0 < coverage["platforms_with_keyword_matches"] <= len(PLATFORM_ALIASES)
    assert 0 <= coverage["multi_platform_raw_link_mentions"] <= 15175
    assert 0 <= coverage["unclassified_raw_link_mentions"] <= 15175
    assert coverage["source_content_or_hardware_verified"] is False
    assert coverage["crawler_authorized"] is False
    assert coverage["training_authorized"] is False
    assert coverage["memory_promotion_authorized"] is False


def test_each_platform_reports_raw_links_deduplicated_urls_and_host_coverage(coverage):
    for item in coverage["platforms"]:
        assert item["raw_link_mentions"] >= item["canonical_candidate_urls"]
        assert item["canonical_candidate_urls"] >= item["distinct_hosts"]
        assert item["canonical_candidate_urls"] <= coverage[
            "canonical_distinct_urls_global"]
        assert item["rights_risk_keyword_link_mentions"] <= item[
            "raw_link_mentions"]
        assert len(item["metadata_examples"]) <= 2
        assert item["metadata_examples"] == sorted(item["metadata_examples"])
        assert item["training_authorized"] is False
        assert item["rights_approved"] is False
        assert item["coverage_status"] in (
            "keyword_discovered_not_verified", "no_matching_metadata_observed")


def test_platform_census_cannot_claim_independence_legality_or_missing_support(coverage):
    assert coverage["metadata_keyword_overlap_is_not_independent_evidence"]
    assert coverage["lack_of_metadata_match_is_not_proof_of_no_support"]
    assert coverage["legal_rights_review_required"]
    assert coverage["unclassified"]["potentially_unlabeled_platforms"]
    assert coverage["unclassified"]["training_authorized"] is False


def test_platform_scan_rejects_unbounded_sampling_or_non_boolean_option():
    registry = read_source_registry(REGISTRY)
    for limit in (-1, True, 11, 1.5, "5"):
        with pytest.raises(ValueError, match="samples per platform"):
            platform_discovery_matrix(registry, samples_per_platform=limit)
    with pytest.raises(ValueError, match="include_unclassified"):
        platform_discovery_matrix(registry, include_unclassified=1)


def test_incomplete_or_reordered_source_chain_cannot_be_reported(coverage, monkeypatch):
    import skeleton.ai.game_builder.dragon_platform_coverage as module
    from skeleton.ai.game_builder.dragon_discovery_reconciled import _chain
    documents = _chain()
    monkeypatch.setattr(module, "_chain", lambda: documents[:-1])
    with pytest.raises(ValueError):
        platform_discovery_matrix(read_source_registry(REGISTRY))
