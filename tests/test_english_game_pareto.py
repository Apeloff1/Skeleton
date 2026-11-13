"""English game Pareto pack: disjoint holdouts, a read-only probe, and a short SGD fit."""
from __future__ import annotations

from pathlib import Path

from skeleton.ai.runtime.inference.english_game_pareto import (
    CURRICULUM,
    first_install_english_game_capabilities,
    holdout_documents,
    logic_documents,
    pareto_score,
    train_documents,
    train_english_game_pareto,
    validate_curriculum,
)


def test_curriculum_is_disjoint_and_covers_scale_and_factors():
    counts = validate_curriculum()
    assert counts["families"] == 8
    assert counts["train"] == 48
    assert counts["holdout"] == 16
    blob = "\n".join(train_documents())
    for text in holdout_documents():
        assert text not in blob
    graphic = "\n".join(train_documents(family="graphics_scale"))
    assert "65536" in graphic
    assert "32768" in graphic and "16384" in graphic
    assert "divisor 2" in graphic
    character = "\n".join(train_documents(family="character_coherence"))
    for token in ("skin tone", "eye colour", "hair colour", "clothing"):
        assert token in character
    items = "\n".join(train_documents(family="items"))
    assert "item kind" in items and "item colour" in items
    assert "vertical slice" in "\n".join(train_documents(family="pareto_scope"))


def test_each_family_has_a_high_value_lesson():
    for name, family in CURRICULUM.items():
        best = max(family["train"], key=pareto_score)
        assert pareto_score(best) >= 20
        assert best[0] == 5


def test_logic_subset_is_smaller_and_still_disjoint():
    logic = logic_documents()
    assert len(logic) == 18
    assert set(logic).issubset(set(train_documents()))
    held = "\n".join(holdout_documents())
    for text in logic:
        assert text not in held


def test_probe_does_not_train_or_load_weights(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("probe touched training")

    monkeypatch.setattr(
        "skeleton.ai.runtime.inference.neural.NumpyRecurrentLM.train",
        boom,
    )
    monkeypatch.setattr(
        "skeleton.ai.runtime.inference.neural.NumpyRecurrentLM.train_document",
        boom,
    )
    report = first_install_english_game_capabilities()
    assert report["training_authorized"] is False
    assert report["promotion"] is False
    assert report["weights_loaded"] is False
    assert report["train_document_count"] == 48
    assert report["scale_example"] == {
        "source_tier": 32768,
        "target_tier": 16384,
        "divisor": 2,
        "high_tier": 65536,
        "allocates_full_tier_buffer": False,
    }
    assert report["perfect_builder_claimed"] is False
    assert report["imports_scale_ladder_module"] is False


def test_source_does_not_import_the_scale_branch():
    source = Path("skeleton/ai/runtime/inference/english_game_pareto.py").read_text(encoding="utf-8")
    assert "jeeves_game_scale_ladder" not in source
    assert "argon_chunk_field" not in source


def test_short_sgd_fit_stays_unpromoted():
    result = train_english_game_pareto(
        epochs=1,
        hidden_size=8,
        seed=3,
        learning_rate=0.05,
        documents=train_documents(family="pareto_scope"),
        holdouts=holdout_documents(family="pareto_scope"),
        model_id="english-game-pareto-test",
    )
    assert result["promotion"] is False
    assert result["canonical_replaced"] is False
    assert result["perfect_builder_claimed"] is False
    assert result["byte_loss_is_gameplay_quality"] is False
    assert result["epochs"] == 1
    assert result["sequence_count"] == 6
    assert result["train_loss_final"] > 0
    assert result["holdout_loss_after"] > 0
    assert result["model_digest"]
