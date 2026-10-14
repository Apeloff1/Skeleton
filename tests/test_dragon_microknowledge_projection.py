"""Retrieval indexing contract independent of Dragon companion/UI runtime."""
import sqlite3
from dataclasses import replace
from hashlib import sha256
import pytest

from skeleton.ai.webcrawler.dragon_knowledge_graph import DragonKnowledgeGraph, KnowledgeConcept
from skeleton.ai.webcrawler.dragon_microknowledge import DragonMicroKnowledge
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample, plan_resources


def sample():
    return HardwareSample(256 * 1024**2, 4, .1, .9, True, False, 10)


def context(db=None):
    db = db or sqlite3.connect(":memory:")
    graph = DragonKnowledgeGraph(db)
    cache = DragonMicroKnowledge(graph)
    plan = plan_resources(sample(), now=10, foreground=True)
    return graph, cache, plan


def add(graph, cache, owner="alice", *, concept_id="combat", text="Turn based combat has stamina", expires=60):
    graph.put_concept(owner, KnowledgeConcept(concept_id, "gameplay", text), authorized=True)
    cache.index(owner, concept_id, {"genre": "rpg", "era": "modern"},
                evidence_ref="source1", expires_at=expires, authorized=True)


def test_retrieval_requires_canonical_indexed_concept_and_active_evidence():
    graph, cache, plan = context()
    with pytest.raises(ValueError, match="canonical concept"):
        cache.index("alice", "missing", {}, evidence_ref="source", expires_at=60, authorized=True)
    add(graph, cache)
    active = cache.retrieve("alice", "combat stamina", {"genre": "rpg"}, plan, now=10, authorized=True)
    assert len(active.hits) == 1
    assert active.hits[0].concept_id == "combat"
    assert active.hits[0].trust == "untrusted_reference"
    assert active.candidates_examined == 1
    assert len(active.context_digest) == 64
    assert cache.retrieve("alice", "combat", {}, plan, now=60, authorized=True).hits == ()


def test_owner_and_facets_are_hard_retrieval_boundaries():
    graph, cache, plan = context()
    add(graph, cache)
    assert cache.retrieve("bob", "combat", {"genre": "rpg"}, plan, now=10, authorized=True).hits == ()
    assert cache.retrieve("alice", "combat", {"genre": "platformer"}, plan, now=10, authorized=True).hits == ()
    assert cache.retrieve("alice", "combat", {"genre": "rpg"}, plan, now=10, authorized=True).hits
    with pytest.raises(ValueError):
        cache.retrieve("alice", "combat", {"unknown": "rpg"}, plan, now=10, authorized=True)


def test_authentication_cannot_be_inferred_from_query_or_existing_index():
    graph, cache, plan = context()
    add(graph, cache)
    with pytest.raises(PermissionError):
        cache.retrieve("alice", "combat", {}, plan, now=10, authorized=False)
    with pytest.raises(PermissionError):
        cache.index("alice", "combat", {}, evidence_ref="source", expires_at=60, authorized=False)
    with pytest.raises(PermissionError):
        cache.remove("alice", "combat", authorized=False)


@pytest.mark.parametrize("bad_clock", [None, "10", True, -1, float("inf"), float("nan")])
def test_hostile_time_values_raise_typed_validation_error(bad_clock):
    _, cache, plan = context()
    with pytest.raises(ValueError, match="invalid microknowledge query"):
        cache.retrieve("alice", "combat", {}, plan, now=bad_clock, authorized=True)


def test_projection_detects_source_drift_instead_of_trusting_cached_facts():
    graph, cache, plan = context()
    add(graph, cache)
    graph.db.execute("UPDATE dragon_knowledge_concepts SET statement='tampered' WHERE owner='alice'")
    graph.db.commit()
    with pytest.raises(ValueError, match="drift"):
        cache.retrieve("alice", "combat", {}, plan, now=10, authorized=True)


def test_deletion_scrubs_postings_and_facets_without_cross_owner_cleanup():
    graph, cache, plan = context()
    add(graph, cache)
    add(graph, cache, "bob")
    cache.remove("alice", "combat", authorized=True)
    assert cache.retrieve("alice", "combat", {}, plan, now=10, authorized=True).hits == ()
    assert len(cache.retrieve("bob", "combat", {}, plan, now=10, authorized=True).hits) == 1
    for table in ("dragon_microknowledge", "dragon_micro_postings", "dragon_micro_facets"):
        assert graph.db.execute(f"SELECT COUNT(*) FROM {table} WHERE owner='alice'").fetchone()[0] == 0
        assert graph.db.execute(f"SELECT COUNT(*) FROM {table} WHERE owner='bob'").fetchone()[0] > 0


def test_retrieval_respects_context_candidate_and_chunk_budgets():
    graph, cache, plan = context()
    add(graph, cache)
    no_context = replace(plan, context_bytes=0)
    assert cache.retrieve("alice", "combat", {}, no_context, now=10, authorized=True).hits == ()
    limited = replace(plan, retrieval_candidates=0)
    assert cache.retrieve("alice", "combat", {}, limited, now=10, authorized=True).hits == ()
    with pytest.raises(ValueError, match="invalid retrieval plan"):
        cache.retrieve("alice", "combat", {}, None, now=10, authorized=True)


def test_index_replacement_does_not_keep_stale_facet_or_postings():
    graph, cache, plan = context()
    add(graph, cache)
    cache.index("alice", "combat", {"genre": "strategy"},
                evidence_ref="source2", expires_at=60, authorized=True)
    assert cache.retrieve("alice", "combat", {"genre": "rpg"}, plan, now=10, authorized=True).hits == ()
    result = cache.retrieve("alice", "combat", {"genre": "strategy"}, plan, now=10, authorized=True)
    assert result.hits[0].evidence_ref == "source2"
