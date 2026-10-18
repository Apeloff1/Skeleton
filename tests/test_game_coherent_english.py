"""Coherent English game passages stay on one cast and off the holdouts."""
from __future__ import annotations

import tempfile
from pathlib import Path

from skeleton.ai.runtime.inference.game_coherent_english import (
    FOCUS,
    TRILLION_WORDS,
    assess,
    budget_forecast,
    coherent_holdouts,
    iter_training_passages,
    render_passage,
    train_coherent_words,
    training_stop,
    validate_passages,
)
from skeleton.ai.runtime.inference.game_corpus_stream import (
    HOLDOUT_SERIAL,
    TEMPLATES,
    holdout_documents,
    training_serial,
)


def test_every_domain_passage_is_coherent_english():
    report = validate_passages()
    assert report["domains"] == len(TEMPLATES) == len(FOCUS)
    assert report["checked"] == len(TEMPLATES) * 4
    for domain in ("legal", "copyright", "assets", "music", "world", "story"):
        text = render_passage(domain, training_serial(0))
        judged = assess(text)
        assert judged["coherent"] is True
        assert judged["english"] is True
        assert judged["words"] >= 40
        assert judged["role"] in text
        assert text.count(judged["place"]) >= 2
        assert text.count(judged["asset"]) >= 2


def test_one_serial_keeps_the_same_cast_and_the_contradiction_breaks_it():
    text = render_passage("music", 40)
    other = render_passage("world", 40)
    bad = render_passage("music", 40, contradict=True)
    music = assess(text)
    world = assess(other)
    assert music["role"] == world["role"]
    assert music["place"] == world["place"]
    assert music["asset"] == world["asset"]
    assert music["coherent"] is True
    assert assess(bad)["coherent"] is False
    assert text.split(". ")[:4] == bad.split(". ")[:4]
    assert "discards the written rule" in bad
    assert "the build stops" in text


def test_training_words_are_not_holdout_lines():
    reserved = set(holdout_documents()) | set(coherent_holdouts())
    produced = 0
    seen = set()
    for domain, text, count in iter_training_passages(12_000):
        assert text not in reserved
        assert assess(text)["coherent"] is True
        assert str(HOLDOUT_SERIAL) not in text
        produced += count
        seen.add(domain)
    assert produced >= 12_000
    assert seen == set(TEMPLATES)


def test_a_short_pass_trains_without_promoting():
    root = Path(tempfile.mkdtemp())
    receipt = train_coherent_words(
        word_budget=400,
        peak_lr=3e-5,
        hidden=16,
        source=None,
        expected_digest=None,
        checkpoint_dir=root,
        chunk_docs=2,
        ledger_path=None,
    )
    assert receipt["words_trained"] >= 400
    assert receipt["words_kept"] <= receipt["words_trained"]
    assert receipt["passages"] >= 1
    assert receipt["language"] == "english"
    assert receipt["coherent_corpus"] is True
    assert receipt["promotion"] is False
    assert receipt["service_checkpoint_touched"] is False
    assert receipt["byte_loss_is_gameplay_quality"] is False
    assert receipt["adamw"]["betas"] == [0.9, 0.999]
    assert receipt["adamw"]["weight_decay"] == 0.01
    assert set(receipt["official_tracks"]) == set(receipt["torch_best_tracks"])
    assert "gap" in receipt["coherence_before"]
    assert receipt["coherence_after"]["ordered_nll"] > 0
    assert receipt["budget_met"] is True
    assert receipt["stop_reason"] == "budget"


def test_a_trillion_word_budget_stops_on_a_plateau_instead_of_claiming_the_total():
    assert TRILLION_WORDS == 1_000_000_000_000
    assert training_stop(100, TRILLION_WORDS, stall=8, plateau_rejects=8) == "plateau"
    assert training_stop(TRILLION_WORDS, TRILLION_WORDS, stall=0, plateau_rejects=8) == "budget"
    assert training_stop(100, TRILLION_WORDS, stall=3, plateau_rejects=8) is None
    forecast = budget_forecast(2_000, 1.0, TRILLION_WORDS)
    assert forecast["budget_met"] is False
    assert forecast["words_per_second"] == 2_000
    assert forecast["projected_seconds"] == TRILLION_WORDS / 2_000
