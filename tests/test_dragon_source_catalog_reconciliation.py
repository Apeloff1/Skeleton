"""Pure no-network assertions for authenticated Git-blob catalog extraction."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha1

import pytest
from skeleton.ai.game_builder.dragon_source_catalog import (
    canonical_source_url, extract_catalog, merge_catalogs,
)
from skeleton.ai.game_builder.contracts import canonical_digest

STAMP = "2026-10-12T12:00:00Z"


def reseal_extraction(catalog: dict) -> dict:
    """Recalculate an untrusted receipt to reach the independent shape guards."""
    catalog["catalog_digest"] = canonical_digest({
        key: catalog[key]
        for key in ("manifest", "sources", "rejected_url_count")
    })
    return catalog


def git_blob(content: str) -> str:
    raw = content.encode("utf-8")
    return sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def read_catalog(content: str, *, url: str = "https://example.org/index"):
    return extract_catalog(
        content, catalog_url=url, blob_sha=git_blob(content), observed_at=STAMP,
    )


def test_canonical_link_identity_removes_only_tracking_parameters():
    assert canonical_source_url(
        "https://Example.com/articles?utm_source=a&topic=game&gclid=z"
    ) == "https://example.com/articles?topic=game"
    for invalid in (
        "http://localhost/", "http://127.0.0.1/",
        "https://private.local/file", "https://user:pw@example.com/",
        "https://example.com:8443/",
    ):
        with pytest.raises(ValueError):
            canonical_source_url(invalid)


def test_catalog_only_discovers_leads_without_fetching_or_approving():
    source = "# Sources\nhttps://example.com/game-guide\nhttps://example.com/game-guide?utm_campaign=a\n"
    one = read_catalog(source)
    assert one["manifest"]["git_blob_sha"] == git_blob(source)
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


def test_git_object_identity_is_bound_to_utf8_bytes_not_declared_string():
    source = "https://example.com/one"
    with pytest.raises(ValueError, match="do not match"):
        extract_catalog(source, catalog_url="https://example.org/index",
                        blob_sha="1" * 40, observed_at=STAMP)
    assert read_catalog(source)["manifest"]["git_blob_sha"] == git_blob(source)
    # Same Git blob identity cannot be assigned to a different body.
    with pytest.raises(ValueError, match="do not match"):
        extract_catalog("https://example.com/two",
                        catalog_url="https://example.org/index",
                        blob_sha=git_blob(source), observed_at=STAMP)


def test_untrusted_catalog_cannot_promote_leads_or_forge_custody():
    base = read_catalog("https://example.com/reference")
    changes = (
        ("training_authorized", True), ("rights", "cleared"),
        ("availability", "fetched"), ("host", "attacker.example"),
    )
    for field, value in changes:
        forged = deepcopy(base)
        forged["sources"][0][field] = value
        with pytest.raises(ValueError):
            merge_catalogs([forged])
    bad_lineage = deepcopy(base)
    bad_lineage["sources"][0]["discoveries"][0]["catalog_id"] = "catalog-" + "e" * 40
    with pytest.raises(ValueError, match="lineage"):
        merge_catalogs([reseal_extraction(bad_lineage)])


def test_manifest_custody_rejects_unknown_fields_and_noncanonical_links():
    base = read_catalog("https://example.com/reference")
    extra_authority = deepcopy(base)
    extra_authority["manifest"]["source_authorized"] = True
    with pytest.raises(ValueError, match="manifest fields"):
        merge_catalogs([reseal_extraction(extra_authority)])
    alias = deepcopy(base)
    alias["manifest"]["url"] = "https://EXAMPLE.org/index?utm_campaign=forged"
    with pytest.raises(ValueError, match="not canonical"):
        merge_catalogs([reseal_extraction(alias)])


def test_incompatible_observation_cannot_rebind_one_git_blob():
    base = read_catalog("https://example.com/reference")
    forged = deepcopy(base)
    forged["manifest"]["observed_at"] = "2026-10-13T00:00:00Z"
    with pytest.raises(ValueError, match="conflicting catalog identity"):
        merge_catalogs([base, forged])


def test_catalog_extraction_receipt_detects_mutated_sources_and_custody():
    base = read_catalog("https://example.com/reference")
    assert base["catalog_digest"] == canonical_digest({
        key: base[key] for key in ("manifest", "sources", "rejected_url_count")
    })
    forged = deepcopy(base)
    forged["sources"][0]["discoveries"][0]["line"] = 90
    with pytest.raises(ValueError, match="extraction receipt"):
        merge_catalogs([forged])
    extra = deepcopy(base)
    extra["sources"][0]["approved"] = True
    with pytest.raises(ValueError, match="extraction receipt"):
        merge_catalogs([extra])
    # A recomputed untrusted digest still cannot grant rights or permissions.
    clearance = deepcopy(base)
    clearance["sources"][0]["training_authorized"] = True
    with pytest.raises(ValueError, match="cannot carry approvals"):
        merge_catalogs([reseal_extraction(clearance)])
    unknown = deepcopy(base)
    unknown["sources"][0]["external_ranking_claim"] = 1
    with pytest.raises(ValueError, match="source fields"):
        merge_catalogs([reseal_extraction(unknown)])
