"""Tests for F-10 prefix ImproveLoop composition (prefix-text variants)."""

from __future__ import annotations

from skeleton.intelligence.improve_loop import ImproveLoop
from skeleton.intelligence.prefix_improve import (
    AnswerQualitySignal,
    PrefixImprover,
    adapt_plane_learner,
    default_prefix_generator,
    improve_prefix,
    mutate_prefix_variant,
    seed_from_renderer,
    seed_from_segments,
)
from skeleton.memory.prefix_renderer import (
    PrefixRegistry,
    PrefixRenderer,
    PrefixSegment,
)
from skeleton.retrieval.plane_weights import PlaneWeightLearner


def _seed():
    return seed_from_segments(
        "test:prefix",
        [
            PrefixSegment("persona", "You are a careful tutor. Ask before telling."),
            PrefixSegment("laws", "Mastery before progression. Errors are data."),
            PrefixSegment("stages", "Onboarding then Foundation then Growth."),
        ],
    )


def test_mutate_rotates_and_is_deterministic():
    seed = _seed()
    a = mutate_prefix_variant(seed, 1)
    b = mutate_prefix_variant(seed, 1)
    assert a.segments[0].name == "laws"
    assert a.sha == b.sha
    assert a.sha != seed.sha


def test_mutate_injects_candidate_bodies():
    seed = _seed()
    candidates = {
        "persona": [
            "You are a Socratic tutor. Never give the answer first.",
        ],
    }
    # Family 3 lands on iteration 3, 8, ...
    variant = mutate_prefix_variant(seed, 3, candidates=candidates)
    persona = next(s for s in variant.segments if s.name == "persona")
    assert "Socratic" in persona.text


def test_improve_with_fake_scorer_keeps_better_variant():
    seed = _seed()
    preferred_order = ("laws", "stages", "persona")  # left-rotate of seed

    def evaluate(variant):
        names = tuple(s.name for s in variant.segments)
        if names == preferred_order:
            return 0.95
        if names == tuple(s.name for s in seed.segments):
            return 0.40
        return 0.50

    out = improve_prefix(
        seed,
        evaluate,
        loop=ImproveLoop(max_iterations=5, patience=4),
        register_on_improve=False,
    )
    assert out.best_score == 0.95
    assert out.best_variant is not None
    assert tuple(s.name for s in out.best_variant.segments) == preferred_order
    assert any(it.improved for it in out.result.iterations)


def test_prefix_improver_registers_best_on_registry():
    seed = _seed()
    registry = PrefixRegistry()

    def evaluate(variant):
        names = tuple(s.name for s in variant.segments)
        if names == ("stages", "persona", "laws"):
            return 0.9
        return 0.2

    improver = PrefixImprover(
        loop=ImproveLoop(max_iterations=4, patience=3),
        registry=registry,
        generate=default_prefix_generator(),
    )
    out = improver.improve(seed, evaluate)
    assert out.registered is True
    stored = registry.get("test:prefix")
    assert stored is not None
    assert stored.sha == out.best_variant.sha


def test_answer_quality_signal_scorer():
    seed = _seed()
    signal = AnswerQualitySignal()
    mutated = mutate_prefix_variant(seed, 1)
    signal.record(seed.sha, 0.2)
    signal.record(mutated.sha, 0.85)
    scorer = signal.scorer(default=0.0)
    assert scorer(seed) == 0.2
    assert scorer(mutated) == 0.85

    out = improve_prefix(
        seed,
        scorer,
        loop=ImproveLoop(max_iterations=3, patience=3),
        generate=default_prefix_generator(),
        register_on_improve=False,
    )
    assert out.best_score == 0.85
    assert out.best_variant.sha == mutated.sha


def test_adapt_plane_learner_uses_signal_when_present():
    learner = PlaneWeightLearner()
    learner.observe(["rag", "cag"], all_planes=["rag", "cag", "mag", "kag"])
    signal = AnswerQualitySignal()
    seed = _seed()
    signal.record(seed.sha, 0.77)
    scorer = adapt_plane_learner(learner, signal=signal, default=0.1)
    assert scorer(seed) == 0.77
    other = mutate_prefix_variant(seed, 1)
    plane_score = scorer(other)
    assert 0.0 < plane_score < 1.0


def test_seed_from_renderer_jeeves():
    renderer = PrefixRenderer()
    variant = seed_from_renderer(renderer)
    assert variant.key == PrefixRenderer.JEEVES_SYSTEM_KEY
    assert len(variant.segments) == 3
    assert variant.segments[0].name == "persona"
    built = renderer.jeeves_system_prefix()
    assert variant.sha == built.sha
