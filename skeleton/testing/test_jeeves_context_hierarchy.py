from __future__ import annotations

from skeleton.jeeves.agent.context_pipeline import (
    ContextSourceAdapter,
    ContextSourceKind,
    ContextTier,
    LayeredContextResolver,
    ResolutionPolicy,
    SourceRecord,
)
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex, MemoryGamePolicy


def _namespace() -> MemoryNamespace:
    return MemoryNamespace("tenant", "user", "workspace", "session")


def test_high_confidence_index_card_short_circuits_deeper_stores() -> None:
    calls = {"journal": 0, "database": 0}

    def journal_search(query: str, limit: int, tags: tuple[str, ...]):
        calls["journal"] += 1
        return (
            SourceRecord("journal-1", "journal", ContextSourceKind.JOURNAL, query, 1.0, 1.0, 1.0, cost=0.5),
        )

    def database_search(query: str, limit: int, tags: tuple[str, ...]):
        calls["database"] += 1
        return (
            SourceRecord("db-1", "db", ContextSourceKind.DATABASE, query, 1.0, 1.0, 1.0, cost=0.1),
        )

    cards = MemoryGameIndex(
        policy=MemoryGamePolicy(
            minimum_score=0.01,
            minimum_fast_path_coverage=0.50,
            minimum_fast_path_confidence=0.05,
        ),
        clock=lambda: 100.0,
    )
    namespace = _namespace()
    query = "prefers deterministic compiler passes with provenance"
    card = cards.capture_interaction(
        namespace,
        query,
        trust=1.0,
        salience=1.0,
        surprise=0.4,
        provenance=("interaction-event-1",),
    )
    resolver = LayeredContextResolver(
        cards=cards,
        memory=MemoryManager(clock=lambda: 100.0),
        adapters=(
            ContextSourceAdapter("db", ContextSourceKind.DATABASE, database_search),
            ContextSourceAdapter("journal", ContextSourceKind.JOURNAL, journal_search),
        ),
        policy=ResolutionPolicy(
            stop_coverage=0.50,
            stop_confidence=0.05,
            stop_trust=0.50,
            minimum_item_score=0.01,
        ),
    )

    result = resolver.resolve(namespace, query)
    assert result.fast_path is True
    assert result.stopped_at is ContextTier.INDEX_CARD
    assert calls == {"journal": 0, "database": 0}
    assert result.items[0].item_id == card.card_id
    assert "interaction-event-1" in result.items[0].evidence_ids
    assert result.stages[0].tier is ContextTier.INDEX_CARD


def test_weak_card_recall_escalates_to_structured_and_narrative_context() -> None:
    calls: list[str] = []

    def database_search(query: str, limit: int, tags: tuple[str, ...]):
        calls.append("database")
        return (
            SourceRecord(
                "db-1",
                "database",
                ContextSourceKind.DATABASE,
                "compiler historical metadata only",
                relevance=0.25,
                trust=0.8,
                confidence=0.5,
                cost=0.2,
            ),
        )

    def journal_search(query: str, limit: int, tags: tuple[str, ...]):
        calls.append("journal")
        return (
            SourceRecord(
                "journal-1",
                "journal",
                ContextSourceKind.JOURNAL,
                query,
                relevance=1.0,
                trust=1.0,
                confidence=1.0,
                cost=0.4,
                evidence_ids=("journal-event-7",),
            ),
        )

    namespace = _namespace()
    cards = MemoryGameIndex(
        policy=MemoryGamePolicy(
            minimum_score=0.01,
            minimum_fast_path_coverage=0.99,
            minimum_fast_path_confidence=0.99,
        ),
        clock=lambda: 1000.0,
    )
    cards.capture_interaction(namespace, "unrelated old preference", trust=0.5, salience=0.4)
    resolver = LayeredContextResolver(
        cards=cards,
        memory=MemoryManager(clock=lambda: 1000.0),
        adapters=(
            ContextSourceAdapter("database", ContextSourceKind.DATABASE, database_search),
            ContextSourceAdapter("journal", ContextSourceKind.JOURNAL, journal_search),
        ),
        policy=ResolutionPolicy(
            stop_coverage=0.80,
            stop_confidence=0.75,
            stop_trust=0.70,
            minimum_item_score=0.01,
            minimum_deep_gain=0.0,
            maximum_tier=ContextTier.JOURNAL,
        ),
    )

    query = "why did the semantic compiler choose provenance bearing IR"
    result = resolver.resolve(namespace, query)
    assert result.fast_path is False
    assert calls == ["database", "journal"]
    assert result.stopped_at is ContextTier.JOURNAL
    assert any(item.source == "journal" and "journal-event-7" in item.evidence_ids for item in result.items)
    tiers = [stage.tier for stage in result.stages]
    assert tiers[0] is ContextTier.INDEX_CARD
    assert ContextTier.SCOPED_MEMORY in tiers
    assert ContextTier.DATABASE in tiers
    assert ContextTier.JOURNAL in tiers


def test_context_adapter_tiers_are_monotonic_and_explicit() -> None:
    assert ContextTier.INDEX_CARD < ContextTier.SCOPED_MEMORY < ContextTier.CONTEXT_REPOSITORY
    assert ContextTier.CACHE < ContextTier.DATABASE < ContextTier.LOG < ContextTier.JOURNAL < ContextTier.DIARY
    assert ContextTier.DIARY < ContextTier.ANNAL < ContextTier.CHRONICLE < ContextTier.ARCHIVE
