"""Self-learn practice stays off the holdouts and reviews weak concepts first."""
from __future__ import annotations

from skeleton.ai.runtime.inference.english_game_pareto import holdout_documents
from skeleton.ai.runtime.inference.game_self_learn import (
    leaks_holdout,
    practice_by_concept,
    practice_documents,
    review_documents,
    review_order,
)


def test_practice_is_large_and_holdout_free():
    docs = practice_documents()
    assert len(docs) >= 400
    assert len(docs) == len(set(docs))
    for text in docs:
        assert len(text) >= 40
        assert leaks_holdout(text) is False
    for held in holdout_documents():
        assert held not in "\n".join(docs)


def test_review_puts_the_weakest_concept_first():
    grouped = practice_by_concept()
    losses = {name: 1.0 for name in grouped}
    losses["tick"] = 3.5
    losses["scale"] = 2.2
    order = review_order(losses)
    assert order[0] == "tick"
    assert order[1] == "scale"
    reviewed = review_documents(losses, rounds=2)
    assert reviewed[0] in grouped["tick"]
    assert len(reviewed) == 2 * sum(len(lines) for lines in grouped.values())


def test_a_holdout_window_is_rejected():
    sample = holdout_documents()[0]
    assert leaks_holdout(sample) is True
    assert leaks_holdout(sample[:40]) is True


def test_focused_review_and_self_learn_pass_improve_weak_concepts():
    from skeleton.ai.runtime.inference.game_self_learn import (
        concept_losses,
        focused_review_documents,
        self_learn_pass,
    )
    from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NumpyRecurrentLM

    grouped = practice_by_concept()
    losses = {name: 1.0 for name in grouped}
    losses["tick"] = 4.0
    losses["scale"] = 3.0
    focused = focused_review_documents(losses, top_concepts=2, rounds=2, include_tail=True)
    assert focused[0] in grouped["tick"]
    assert len(focused) < len(review_documents(losses, rounds=2))

    model = NumpyRecurrentLM(model_id="self-learn-test", config=NeuralLMConfig(hidden_size=8, seed=13))
    eval_docs = grouped["tick"][:2]
    report = self_learn_pass(
        model,
        rounds=1,
        top_concepts=2,
        learning_rate=0.05,
        optimizer="adamw",
        weight_decay=0.01,
        eval_documents=eval_docs,
    )
    assert report["improved"] is True
    assert report["final_eval_loss"] <= report["initial_eval_loss"]
    measured = concept_losses(model)
    assert set(measured.keys()) == set(grouped.keys())


def test_multi_stage_game_creation_finetune_and_mastery_report():
    from skeleton.ai.runtime.inference.game_self_learn import (
        GAME_CREATION_STAGES,
        all_holdout_documents,
        cross_curriculum_losses,
        finetune_for_game_creation,
        game_creation_mastery_report,
        leaks_any_holdout,
        pareto_weighted_curriculum,
        stage_curriculum_documents,
    )
    from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NumpyRecurrentLM

    all_held = all_holdout_documents()
    assert len(all_held) >= 60
    assert leaks_any_holdout(all_held[0]) is True

    entries = pareto_weighted_curriculum()
    assert len(entries) >= 150
    for item in entries:
        assert leaks_any_holdout(str(item["text"])) is False
        assert int(item["repetitions"]) in {1, 2, 3}

    for st in GAME_CREATION_STAGES:
        st_docs = stage_curriculum_documents(st, include_practice=False, pareto_repeat=False)
        assert len(st_docs) > 0

    model = NumpyRecurrentLM(model_id="finetune-game-test", config=NeuralLMConfig(hidden_size=8, seed=21))
    eval_sample = stage_curriculum_documents("stage_1_foundation", include_practice=False, pareto_repeat=False)[:4]
    receipt = finetune_for_game_creation(
        model,
        stages=("stage_1_foundation", "stage_2_world_combat_art"),
        epochs_per_stage=1,
        remediation_rounds=1,
        top_weak_concepts=2,
        learning_rate=0.04,
        optimizer="adamw",
        weight_decay=0.01,
        include_practice=False,
        eval_documents=eval_sample,
    )
    assert receipt["eval_improved"] is True
    assert receipt["final_eval_loss"] < receipt["initial_eval_loss"]
    assert receipt["holdout_isolated"] is True
    assert receipt["promoted"] is False

    mastery = game_creation_mastery_report(model)
    assert mastery["pillar_count"] >= 25
    assert 0.0 < float(mastery["mastery_index"]) <= 1.0
    cross = cross_curriculum_losses(model)
    assert "english_pareto_train" in cross and "az_train" in cross and "pareto_v2_train" in cross
