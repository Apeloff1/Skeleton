from skeleton.jeeves.agent.memory_game_index import (
    CardKind,
    MemoryGameIndex,
    RelationKind,
    SourceTier,
)


def _clock():
    state = {"now": 1_000_000.0}

    def read():
        return state["now"]

    return state, read


def test_pair_and_juxtaposition_expand_fast_recall_without_rewriting_sources():
    state, clock = _clock()
    index = MemoryGameIndex(clock=clock)
    first = index.index_source(
        namespace_key="t/u/w",
        source_tier=SourceTier.JOURNAL,
        source_ref="journal:1",
        source_fingerprint="a" * 64,
        cue="red door warning",
        preview="A red door was closed.",
        kind=CardKind.EPISODE_CUE,
        trust=0.9,
        confidence=0.9,
    )
    second = index.index_source(
        namespace_key="t/u/w",
        source_tier=SourceTier.DIARY,
        source_ref="diary:2",
        source_fingerprint="b" * 64,
        cue="quiet room reaction",
        preview="The room became quiet.",
        kind=CardKind.EPISODE_CUE,
        trust=0.9,
        confidence=0.9,
    )
    relation = index.juxtapose((first.card_id, second.card_id), strength=0.9, confidence=0.8)
    packet = index.query("t/u/w", "red door")
    assert packet.direct_hits[0].card.card_id == first.card_id
    assert any(hit.card.card_id == second.card_id for hit in packet.associative_hits)
    assert relation.interpretive is True
    assert index.card(first.card_id).source_fingerprint == "a" * 64


def test_successful_spaced_retrieval_strengthens_card_and_failure_weakens_it():
    state, clock = _clock()
    index = MemoryGameIndex(clock=clock)
    card = index.index_source(
        namespace_key="t/u/w",
        source_tier=SourceTier.LOG,
        source_ref="log:1",
        source_fingerprint="c" * 64,
        cue="compiler regression",
        preview="Compiler pass changed behavior.",
    )
    state["now"] += 48 * 3600
    success = index.retrieval_feedback(card.card_id, success=True, reward=1.0)
    assert success.retrieval_strength > card.retrieval_strength
    state["now"] += 3600
    failed = index.retrieval_feedback(card.card_id, success=False)
    assert failed.retrieval_strength < success.retrieval_strength
    assert failed.successful_retrievals == 1
    assert failed.failed_retrievals == 1


def test_sequence_relations_predict_following_cards():
    _, clock = _clock()
    index = MemoryGameIndex(clock=clock)
    cards = [
        index.index_source(
            namespace_key="t/u/w",
            source_tier=SourceTier.CHRONICLE,
            source_ref=f"chronicle:{i}",
            source_fingerprint=str(i) * 64,
            cue=f"event {i}",
            preview=f"event {i}",
            sequence=i,
        )
        for i in range(3)
    ]
    index.link_sequence([card.card_id for card in cards])
    predicted = index.predicted_next_cards(cards[0].card_id)
    assert predicted
    assert predicted[0][0].card_id == cards[1].card_id


def test_namespace_isolation_is_fail_closed():
    _, clock = _clock()
    index = MemoryGameIndex(clock=clock)
    index.index_source(
        namespace_key="tenant/a/work",
        source_tier=SourceTier.DATABASE,
        source_ref="row:1",
        source_fingerprint="d" * 64,
        cue="secret alpha",
        preview="secret alpha",
        trust=1.0,
    )
    assert index.query("tenant/b/work", "secret alpha").direct_hits == ()


def test_review_queue_uses_retrieval_probability_not_only_recency():
    state, clock = _clock()
    index = MemoryGameIndex(clock=clock)
    weak = index.index_source(
        namespace_key="t/u/w",
        source_tier=SourceTier.CACHE,
        source_ref="cache:weak",
        source_fingerprint="e" * 64,
        cue="rare key",
        preview="rare key",
        salience=1.0,
        trust=1.0,
    )
    # Several failures push retrieval activation below the target.
    for _ in range(3):
        index.retrieval_feedback(weak.card_id, success=False)
    state["now"] += 30 * 24 * 3600
    queue = index.review_queue("t/u/w", target_recall=0.85)
    assert any(card.card_id == weak.card_id for card in queue)


def test_repeated_query_reuses_card_lexical_features() -> None:
    _, clock = _clock()
    index = MemoryGameIndex(clock=clock)
    index.index_source(
        namespace_key="t/u/w",
        source_tier=SourceTier.JOURNAL,
        source_ref="journal:cache",
        source_fingerprint="f" * 64,
        cue="deterministic compiler evidence",
        preview="compiler evidence replay",
        trust=1.0,
    )

    before = index.retrieval_stats()
    first = index.query("t/u/w", "compiler evidence", touch=False)
    warm = index.retrieval_stats()
    second = index.query("t/u/w", "compiler evidence", touch=False)
    after = index.retrieval_stats()

    assert first.fingerprint == second.fingerprint
    assert warm["lexical_cache_misses"] >= before["lexical_cache_misses"]
    assert after["lexical_cache_misses"] == warm["lexical_cache_misses"]
    assert after["lexical_cache_hits"] > warm["lexical_cache_hits"]


def test_interference_uses_inverted_index_instead_of_namespace_full_scan() -> None:
    _, clock = _clock()
    index = MemoryGameIndex(clock=clock)
    target = index.index_source(
        namespace_key="t/u/w",
        source_tier=SourceTier.MEMORY_STORE,
        source_ref="memory:target",
        source_fingerprint="1" * 64,
        cue="rare_alpha rare_beta",
        preview="",
        trust=1.0,
    )
    similar = index.index_source(
        namespace_key="t/u/w",
        source_tier=SourceTier.MEMORY_STORE,
        source_ref="memory:similar",
        source_fingerprint="2" * 64,
        cue="rare_alpha rare_beta neighbor",
        preview="",
        trust=1.0,
    )
    for number in range(100):
        index.index_source(
            namespace_key="t/u/w",
            source_tier=SourceTier.MEMORY_STORE,
            source_ref=f"memory:unrelated:{number}",
            source_fingerprint=f"{number:064x}",
            cue=f"isolated_{number} unique_{number}",
            preview="",
            trust=1.0,
        )

    before = index.retrieval_stats()["interference_candidates"]
    packet = index.query("t/u/w", "rare_alpha", limit=2, touch=False)
    evaluated = index.retrieval_stats()["interference_candidates"] - before

    assert packet.direct_hits[0].card.card_id in {target.card_id, similar.card_id}
    assert evaluated <= 2
    assert evaluated < index.count("t/u/w")


def test_novel_query_fallback_uses_namespace_index_not_global_card_scan() -> None:
    _, clock = _clock()
    index = MemoryGameIndex(clock=clock)
    for namespace in ("tenant/a", "tenant/b"):
        for number in range(25):
            index.index_source(
                namespace_key=namespace,
                source_tier=SourceTier.CACHE,
                source_ref=f"{namespace}:{number}",
                source_fingerprint=f"{number + (100 if namespace.endswith('b') else 0):064x}",
                cue=f"known_{namespace[-1]}_{number}",
                preview="",
                trust=1.0,
            )

    class _NoGlobalValues(dict):
        def values(self):
            raise AssertionError("novel-query fallback scanned global card values")

    index._cards = _NoGlobalValues(index._cards)
    packet = index.query("tenant/a", "completely_novel_token", limit=3, touch=False)

    assert len(packet.direct_hits) == 3
    assert all(hit.card.namespace_key == "tenant/a" for hit in packet.direct_hits)
    assert index.count("tenant/a") == 25
