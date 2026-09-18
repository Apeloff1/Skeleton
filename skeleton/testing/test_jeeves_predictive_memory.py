from skeleton.jeeves.agent.memory_game_index import MemoryGameIndex, SourceTier
from skeleton.jeeves.agent.predictive_memory import PredictiveMemoryEngine


def _card(index, ref, cue):
    return index.index_source(
        namespace_key="tenant/user/work/session",
        source_tier=SourceTier.MEMORY_STORE,
        source_ref=ref,
        source_fingerprint=(ref[-1] if ref[-1].isalnum() else "a") * 64,
        cue=cue,
        preview=cue,
        trust=0.95,
        confidence=0.95,
        salience=0.8,
    )


def test_predictive_memory_learns_observed_transition_and_scores_surprise():
    index = MemoryGameIndex()
    engine = PredictiveMemoryEngine(index)
    a = _card(index, "mem-a", "user asks about compiler")
    b = _card(index, "mem-b", "assistant inspects ir")
    engine.observe(a.card_id, stream_id="dialogue")
    update = engine.observe(b.card_id, stream_id="dialogue")
    assert update.previous_card_id == a.card_id
    assert update.prediction_error > 0.0
    assert update.surprise_bits > 0.0
    assert engine.transition_counts(a.card_id)[b.card_id] == 1.0
    prediction = engine.predict(a.card_id)
    assert prediction.top is not None
    assert prediction.top.target_card_id == b.card_id


def test_prediction_streams_do_not_cross_contaminate():
    index = MemoryGameIndex()
    engine = PredictiveMemoryEngine(index)
    dialogue = _card(index, "mem-d", "dialogue event")
    runtime = _card(index, "mem-r", "runtime event")
    engine.observe(dialogue.card_id, stream_id="dialogue")
    engine.observe(runtime.card_id, stream_id="runtime")
    assert engine.transition_counts(dialogue.card_id) == {}


def test_unexpected_observation_is_prioritized_for_review():
    index = MemoryGameIndex()
    engine = PredictiveMemoryEngine(index)
    a = _card(index, "mem-1", "alpha")
    b = _card(index, "mem-2", "beta")
    c = _card(index, "mem-3", "rare gamma")
    engine.observe(a.card_id, stream_id="s")
    engine.observe(b.card_id, stream_id="s")
    engine.observe(a.card_id, stream_id="s")
    update = engine.observe(c.card_id, stream_id="s")
    assert update.prediction_error > 0.9
    reviewed = engine.review_queue("tenant/user/work/session", limit=3)
    assert any(card.card_id == c.card_id for card in reviewed)
