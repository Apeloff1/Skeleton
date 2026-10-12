"""Exact-blob source custody checks for nine Git-pinned expansion catalogs."""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.game_builder.dragon_almanacs import read_source_registry
from skeleton.ai.game_builder.dragon_discovery_identity_audit import (
    MANIFESTS, PREVIOUS_BATCH_COUNT, PREVIOUS_SUPPLEMENT_COUNT,
    audit_raw_discovery_identity,
)
from skeleton.ai.game_builder.dragon_discovery_reconciled import SOURCE_BATCHES, EXPECTED_RAW_TOTAL

BASELINE = (Path(__file__).resolve().parents[1] /
            "skeleton/ai/game_builder/catalogs/dragon_sources_20261010")


@pytest.fixture(scope="module")
def inventory():
    return audit_raw_discovery_identity(read_source_registry(BASELINE))


def test_frozen_raw_link_custody_matches_git_blobs_and_new_evidence(inventory):
    assert inventory["baseline_raw_links"] == 4405
    assert inventory["historical_supplement_raw_links"] == 10770
    assert inventory["additional_pinned_raw_links"] == 5685
    assert inventory["reconciled_raw_links"] == EXPECTED_RAW_TOTAL
    assert inventory["accepted_source_batches"] == len(SOURCE_BATCHES) == 24
    assert len(MANIFESTS) == 2
    assert PREVIOUS_BATCH_COUNT == 16
    assert PREVIOUS_SUPPLEMENT_COUNT == 10770
    assert inventory["all_source_blob_identities_checked"] is True
    assert inventory["canonical_candidate_urls"] <= EXPECTED_RAW_TOTAL
    assert inventory["canonical_candidate_urls"] > 4405
    assert [x["manifest"] for x in inventory["historical_manifests"]] == list(MANIFESTS)
    assert sum(x["verified_source_files"] for x in inventory["historical_manifests"]) == 16
    assert sum(x["verified_raw_links"] for x in inventory["historical_manifests"]) == 10770


def test_identity_audit_never_converts_catalog_mentions_into_source_authority(inventory):
    for key in ("linked_source_contents_verified", "crawler_authorized",
                "rights_approved", "training_authorized",
                "memory_promotion_authorized"):
        assert inventory[key] is False
    assert all(x["training_authorized"] is False and
               x["source_contents_verified"] is False
               for x in inventory["historical_manifests"])
    assert "docs/ai/evidence/dragon-source-expansion-20261012-batch-0024.json" \
           in inventory["excluded_orphans"]


def test_identity_audit_fails_closed_on_git_blob_mismatch(monkeypatch):
    import skeleton.ai.game_builder.dragon_discovery_identity_audit as module
    monkeypatch.setattr(module, "_git_blob_sha", lambda _: "a" * 40)
    with pytest.raises(ValueError, match="Git blob"):
        audit_raw_discovery_identity(read_source_registry(BASELINE))


def test_identity_audit_limits_detail_and_rejects_boolean_budgets(inventory):
    registry = read_source_registry(BASELINE)
    zero = audit_raw_discovery_identity(registry, detail_limit=0)
    assert zero["historical_manifests"] == []
    assert zero["historical_manifests_omitted"] == 2
    for value in (-1, True, 101, 2.5, "5"):
        with pytest.raises(ValueError, match="detail"):
            audit_raw_discovery_identity(registry, detail_limit=value)
