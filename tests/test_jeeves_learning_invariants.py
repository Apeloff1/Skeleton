"""Adversarial invariants for Jeeves assessment and knowledge state."""

import math

import pytest

from skeleton.jeeves.assessment import (
    AdaptiveTest,
    AssessmentEngine,
    AssessmentError,
    InteractionEvidence,
    SkillModel,
)
from skeleton.jeeves.knowledge import (
    Concept,
    ConceptError,
    EdgeType,
    KnowledgeGraph,
)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"learning_rate": math.nan},
        {"learning_rate": -0.1},
        {"learning_rate": 1.1},
        {"decay_rate": math.inf},
        {"decay_rate": -0.01},
        {"max_skills": 0},
    ],
)
def test_assessment_rejects_invalid_engine_parameters(kwargs):
    with pytest.raises(AssessmentError):
        AssessmentEngine(**kwargs)


def test_assessment_skill_capacity_fails_closed():
    engine = AssessmentEngine(max_skills=1)
    engine.register("python")

    with pytest.raises(AssessmentError, match="capacity"):
        engine.register("rust")

    assert engine.report("python")["skill"] == "python"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"skill_id": "", "correct": True},
        {"skill_id": "python", "correct": 1},
        {"skill_id": "python", "correct": True, "latency_s": -1},
        {"skill_id": "python", "correct": True, "latency_s": math.nan},
        {"skill_id": "python", "correct": True, "hints_used": -1},
        {"skill_id": "python", "correct": True, "hints_used": 1001},
    ],
)
def test_evidence_rejects_poisoned_values(kwargs):
    with pytest.raises(AssessmentError):
        InteractionEvidence(**kwargs)


def test_backwards_clock_does_not_increase_mastery_via_negative_decay():
    ticks = iter([10.0, 9.0, 8.0])
    engine = AssessmentEngine(clock=lambda: next(ticks), learning_rate=0.2, decay_rate=0.1)
    skill = engine.register("python")
    skill.mastery = 0.5

    observed = engine.observe(InteractionEvidence("python", correct=False))

    assert observed.mastery <= 0.5
    assert engine.report("python")["idle_s"] == 0.0


def test_non_finite_clock_is_rejected():
    engine = AssessmentEngine(clock=lambda: math.nan)
    with pytest.raises(AssessmentError, match="clock"):
        engine.register("python")


def test_skill_model_rejects_non_finite_state():
    with pytest.raises(AssessmentError):
        SkillModel("python", mastery=math.nan)


def test_adaptive_threshold_is_bounded():
    adaptive = AdaptiveTest(AssessmentEngine())
    with pytest.raises(AssessmentError):
        adaptive.should_remediate("python", threshold=1.1)


def _three_node_graph():
    graph = KnowledgeGraph()
    graph.add_concept(Concept("a", "A", "test", 0.1))
    graph.add_concept(Concept("b", "B", "test", 0.2))
    graph.add_concept(Concept("c", "C", "test", 0.3))
    return graph


@pytest.mark.parametrize("difficulty", [math.nan, math.inf, -0.1, 1.1])
def test_concept_rejects_non_finite_or_out_of_range_difficulty(difficulty):
    with pytest.raises(ConceptError):
        Concept("x", "X", "test", difficulty)


def test_prerequisite_cycles_are_rejected_at_mutation_time():
    graph = _three_node_graph()
    graph.add_edge("a", "b", EdgeType.PREREQUISITE_OF)
    graph.add_edge("b", "c", EdgeType.PREREQUISITE_OF)

    with pytest.raises(ConceptError, match="cycle"):
        graph.add_edge("c", "a", EdgeType.PREREQUISITE_OF)

    assert graph.learning_path("c", set()) == ["a", "b", "c"]


def test_self_prerequisite_is_rejected():
    graph = _three_node_graph()
    with pytest.raises(ConceptError, match="cycle"):
        graph.add_edge("a", "a", EdgeType.PREREQUISITE_OF)


def test_duplicate_edges_are_idempotent():
    graph = _three_node_graph()
    graph.add_edge("a", "b", EdgeType.PREREQUISITE_OF)
    graph.add_edge("a", "b", EdgeType.PREREQUISITE_OF)
    assert graph.stats()["edges"] == 1


def test_graph_capacity_fails_closed_without_losing_existing_state():
    graph = KnowledgeGraph(max_concepts=1, max_edges=1)
    graph.add_concept(Concept("a", "A", "test"))

    with pytest.raises(ConceptError, match="capacity"):
        graph.add_concept(Concept("b", "B", "test"))

    assert graph.stats()["concepts"] == 1


def test_edge_capacity_fails_closed():
    graph = _three_node_graph()
    graph._max_edges = 1
    graph.add_edge("a", "b", EdgeType.RELATES_TO)
    with pytest.raises(ConceptError, match="capacity"):
        graph.add_edge("b", "c", EdgeType.RELATES_TO)


def test_learning_queries_reject_malformed_known_sets():
    graph = _three_node_graph()
    with pytest.raises(ConceptError, match="known"):
        graph.ready_to_learn(["a"])  # type: ignore[arg-type]
    with pytest.raises(ConceptError, match="known"):
        graph.learning_path("c", {1})  # type: ignore[arg-type]
