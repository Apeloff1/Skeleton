"""Tests for F-10 prompt ImproveLoop (prefix-text variants + answer quality)."""

from __future__ import annotations

from skeleton.intelligence.improve_loop import ImproveLoop
from skeleton.intelligence.prompt_improve import (
    PrefixVariant,
    PromptImproveDriver,
    answer_quality_score,
    improve_prefix_prompt,
    mutate_prefix,
)
from skeleton.retrieval.plane_weights import PlaneWeightLearner


def _seed() -> PrefixVariant:
    return PrefixVariant(
        key="test:prefix",
        text=(
            "You are a careful tutor. Ask before telling. "
            "Mastery before progression. Errors are data."
        ),
    )


def test_mutate_prefix_deterministic_under_seed():
    seed = _seed()
    a = mutate_prefix(seed, seed=7)
    b = mutate_prefix(seed, seed=7)
    c = mutate_prefix(seed, seed=8)
    assert a.text == b.text
    assert a.sha == b.sha
    assert a.sha != seed.sha
    assert a.generation == 1
    assert a.seed_used == 7
    assert c.sha != a.sha


def test_mutate_prefix_families_change_text():
    seed = _seed()
    seen = {mutate_prefix(seed, seed=s).sha for s in range(10)}
    assert len(seen) >= 3


def test_answer_quality_score_empty_and_reference():
    assert answer_quality_score("") == 0.0
    assert answer_quality_score("   ") == 0.0
    good = answer_quality_score(
        "The capital is Oslo. It lies at the head of the Oslofjord.",
        reference="Oslo is the capital of Norway near the Oslofjord.",
    )
    weak = answer_quality_score("nope", reference="Oslo is the capital of Norway.")
    assert 0.0 < weak < good <= 1.0


def test_answer_quality_score_feedback_stats_boost():
    learner = PlaneWeightLearner()
    for _ in range(12):
        learner.observe(["rag", "kag"])
    stats = learner.stats()
    answer = (
        "A solid explanation of the topic with enough detail to be useful. "
        "It covers the main idea and a concrete example."
    )
    base = answer_quality_score(answer, feedback_stats=None)
    boosted = answer_quality_score(answer, feedback_stats=stats)
    assert boosted >= base
    assert boosted <= 1.0
    assert answer_quality_score(answer, feedback_stats={"rates": {}}) == base


def test_driver_keeps_better_variant_via_recorded_scores():
    seed = _seed()
    preferred = mutate_prefix(seed, seed=1)

    driver = PromptImproveDriver(
        loop=ImproveLoop(max_iterations=5, patience=4),
        generate=lambda incumbent, iteration: mutate_prefix(incumbent, seed=iteration),
    )
    driver.record_score(seed, 0.30)
    driver.record_score(preferred, 0.92)

    out = driver.improve(seed)
    assert out.best_score == 0.92
    assert out.best_variant is not None
    assert out.best_variant.sha == preferred.sha
    assert any(it.improved for it in out.result.iterations)


def test_driver_answer_fn_and_feedback_stats():
    seed = _seed()
    learner = PlaneWeightLearner()
    for _ in range(10):
        learner.observe(["rag"])

    def answer_fn(variant: PrefixVariant) -> str:
        if "Also," in variant.text or "Importantly," in variant.text or "Remember:" in variant.text:
            return (
                "Oslo is the capital of Norway. It sits at the head of the Oslofjord "
                "and is the country's largest city."
            )
        return "idk"

    out = improve_prefix_prompt(
        seed,
        loop=ImproveLoop(max_iterations=6, patience=4),
        feedback_stats=learner.stats(),
        answer_fn=answer_fn,
        reference="Oslo is the capital of Norway near the Oslofjord.",
    )
    assert out.feedback_boost_applied is True
    assert out.best_variant is not None
    assert out.best_score > answer_quality_score(
        "idk", reference="Oslo is the capital of Norway."
    )


def test_driver_fallback_without_answer_fn():
    seed = PrefixVariant(key="k", text="Short.")
    out = PromptImproveDriver(
        loop=ImproveLoop(max_iterations=4, patience=3),
        generate=lambda incumbent, iteration: mutate_prefix(incumbent, seed=2),
    ).improve(seed)
    assert out.best_variant is not None
    assert out.best_score >= 0.0
    assert out.stopped_reason in {"patience", "budget", "target"}
