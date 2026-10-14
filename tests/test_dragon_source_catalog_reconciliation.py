"""Pure, no-network assertions for Dragon catalog extraction and URL custody."""
from __future__ import annotations

import pytest
from skeleton.ai.game_builder.dragon_source_catalog import (
    canonical_source_url, extract_catalog, merge_catalogs,
)

BLOB = "1" * 40
STAMP = "2026-10-12T12:00:00Z"


def test_canonical_link_identity_removes_only_tracking_parameters():
    assert canonical_source_url(
        "https://Example.com/articles?utm_source=a&topic=game&gclid=z"
    ) == "https://example.com/articles?topic=game"
    for invalid in (
        "http://localhost/",
        "http://127.0.0.1/",
        "https://private.local/file",
        "https://user:pw@example.com/",
        "https://example.com:8443/",
    ):
        with pytest.raises(ValueError):
            canonical_source_url(invalid)


def test_catalog_only_discovers_leads_without_fetching_or_approving():
    source = "# Sources\nhttps://example.com/game-guide\nhttps://example.com/game-guide?utm_campaign=a\n"
    one = extract_catalog(source, catalog_url="https://example.org/index", blob_sha=BLOB, observed_at=STAMP)
    assert one["manifest"]["linked_content_fetched"] is False
    assert len(one["sources"]) == 1
    item = one["sources"][0]
    assert item["url"] == "https://example.com/game-guide"
    assert item["training_authorized"] is False
    assert item["rights"] == "not_assessed"
    assert item["availability"] == "not_checked"
    result = merge_catalogs([one, one])
    assert result["unique_urls"] == 1
    assert result["approved_sources"] == 0
    assert result["individually_fetched_sources"] == 0


def test_same_git_blob_cannot_be_rebound_to_different_catalog_content():
    one = extract_catalog(
        "https://example.com/one", catalog_url="https://example.org/index",
        blob_sha=BLOB, observed_at=STAMP,
    )
    two = extract_catalog(
        "https://example.com/two", catalog_url="https://example.org/index",
        blob_sha=BLOB, observed_at=STAMP,
    )
    with pytest.raises(ValueError, match="conflicting catalog identity"):
        merge_catalogs([one, two])
