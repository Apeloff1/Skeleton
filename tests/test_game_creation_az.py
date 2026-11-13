"""A-to-Z game creation lessons stay disjoint from their holdouts and from the English pack holdouts."""
from __future__ import annotations

from skeleton.ai.runtime.inference.english_game_pareto import holdout_documents as english_holdouts
from skeleton.ai.runtime.inference.game_creation_az import (
    CURRICULUM,
    first_install_game_creation_probe,
    holdout_documents,
    pareto_score,
    train_documents,
    validate_curriculum,
)


def test_az_curriculum_covers_the_pipeline():
    counts = validate_curriculum()
    assert counts["families"] == 15
    assert counts["train"] == 75
    assert counts["holdout"] == 30
    assert list(CURRICULUM)[0] == "intent"
    assert list(CURRICULUM)[-1] == "ship"
    blob = "\n".join(train_documents())
    for text in holdout_documents():
        assert text not in blob
    for token in ("65536", "32768", "16384", "skin tone", "eye colour", "frame budget"):
        assert token in blob


def test_az_does_not_contain_english_holdouts():
    blob = "\n".join(train_documents())
    for text in english_holdouts():
        assert text not in blob
    for text in holdout_documents():
        assert text not in "\n".join(english_holdouts())


def test_each_stage_has_a_high_value_lesson():
    for family in CURRICULUM.values():
        best = max(family["train"], key=pareto_score)
        assert best[0] == 5
        assert pareto_score(best) >= 14


def test_probe_does_not_train(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("probe trained")

    monkeypatch.setattr(
        "skeleton.ai.runtime.inference.neural.NumpyRecurrentLM.train",
        boom,
    )
    report = first_install_game_creation_probe()
    assert report["training_authorized"] is False
    assert report["promotion"] is False
    assert report["weights_loaded"] is False
    assert report["covers_game_creation_a_to_z"] is True
    assert report["train_document_count"] == 75
    assert "audio" in report["adjacent_topics"]
    assert report["perfect_builder_claimed"] is False
