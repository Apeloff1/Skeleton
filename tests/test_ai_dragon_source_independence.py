"""Tests for conservative provenance-derived source dependency clustering."""
import pytest
from skeleton.ai.webcrawler.dragon_source_independence import (
    SourceProvenance, derive_dependency_clusters,
)


def src(name, digest, uri, parents=(), lineage=()):
    return SourceProvenance(name, digest * 64, uri, parents, lineage)


def test_identical_content_is_not_independent():
    result = derive_dependency_clusters((
        src("a", "a", "https://one.example/a"),
        src("b", "a", "https://two.example/copy"),
    ), authorized=True)
    assert len(result) == 1
    assert "identical_content" in result[0].reasons


def test_canonical_origin_collapses_query_and_fragment():
    result = derive_dependency_clusters((
        src("a", "a", "https://EXAMPLE.com/page?utm=x"),
        src("b", "b", "https://example.com/page#copy"),
    ), authorized=True)
    assert len(result) == 1
    assert "canonical_origin" in result[0].reasons


def test_declared_derivation_is_dependent():
    result = derive_dependency_clusters((
        src("a", "a", "https://a.example/a"),
        src("b", "b", "https://b.example/b", parents=("a",)),
    ), authorized=True)
    assert len(result) == 1
    assert "declared_derivation" in result[0].reasons


def test_shared_lineage_is_dependent():
    result = derive_dependency_clusters((
        src("a", "a", "https://a.example/a", lineage=("wire-1",)),
        src("b", "b", "https://b.example/b", lineage=("wire-1",)),
    ), authorized=True)
    assert len(result) == 1


def test_unrelated_sources_remain_separate():
    result = derive_dependency_clusters((
        src("a", "a", "https://a.example/a"),
        src("b", "b", "https://b.example/b"),
    ), authorized=True)
    assert len(result) == 2


def test_unknown_parent_fails_closed():
    with pytest.raises(ValueError, match="unknown parent"):
        derive_dependency_clusters((
            src("a", "a", "https://a.example/a", parents=("missing",)),
        ), authorized=True)


def test_authorization_required():
    with pytest.raises(PermissionError):
        derive_dependency_clusters((), authorized=False)
