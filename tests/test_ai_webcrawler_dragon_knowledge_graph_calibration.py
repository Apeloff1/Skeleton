"""Dragon knowledge graph and probability calibration regressions."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_knowledge_graph import (
    DragonKnowledgeGraph, KnowledgeConcept, KnowledgeRelation, Relation,
)
from skeleton.ai.webcrawler.dragon_probability_calibration import (
    CalibrationExample, calibration_report,
)


def test_graph_immutable_concepts():
    graph = DragonKnowledgeGraph(sqlite3.connect(":memory:"))
    graph.put_concept("alice", KnowledgeConcept("jump", "mechanics", "Jump buffering"),
                      authorized=True)
    graph.put_concept("alice", KnowledgeConcept("jump", "mechanics", "Jump buffering"),
                      authorized=True)
    with pytest.raises(ValueError, match="immutable"):
        graph.put_concept("alice", KnowledgeConcept("jump", "mechanics", "Other"),
                          authorized=True)


def test_graph_requires_existing_endpoints():
    graph = DragonKnowledgeGraph(sqlite3.connect(":memory:"))
    graph.put_concept("alice", KnowledgeConcept("jump", "mechanics", "Jump"),
                      authorized=True)
    with pytest.raises(ValueError, match="missing"):
        graph.put_relation("alice", KnowledgeRelation(
            "jump", "missing", Relation.CAUSES, "a" * 64, "Evidence",
        ), authorized=True)


def test_graph_traversal_and_audit():
    graph = DragonKnowledgeGraph(sqlite3.connect(":memory:"))
    for key in ("a", "b", "c"):
        graph.put_concept("alice", KnowledgeConcept(key, "mechanics", key),
                          authorized=True)
    for source, target in (("a", "b"), ("b", "c")):
        graph.put_relation("alice", KnowledgeRelation(
            source, target, Relation.REQUIRES, "a" * 64, "Dependency",
        ), authorized=True)
    assert len(graph.neighborhood(
        "alice", "a", authorized=True, max_depth=2,
    )) == 3
    audit = graph.audit("alice", authorized=True)
    assert audit.concept_count == 3
    assert audit.relation_count == 2
    assert audit.dangling_relations == 0


def test_graph_owner_isolation():
    graph = DragonKnowledgeGraph(sqlite3.connect(":memory:"))
    graph.put_concept("alice", KnowledgeConcept("private", "design", "Secret"),
                      authorized=True)
    assert graph.neighborhood("bob", "private", authorized=True) == ()
    assert graph.erase("alice", authorized=True) == 1


def test_calibration_perfect_predictions():
    examples = tuple(
        CalibrationExample(str(i), float(i % 2), bool(i % 2),
                           "independent", "2026")
        for i in range(40)
    )
    report = calibration_report(examples, authorized=True)
    assert report.brier_score == 0
    assert report.expected_calibration_error == 0
    assert report.samples == 40


def test_calibration_identifies_bad_probabilities():
    examples = tuple(
        CalibrationExample(str(i), 0.9, False, "group", "2026")
        for i in range(40)
    )
    report = calibration_report(examples, authorized=True)
    assert report.brier_score > 0.8
    assert report.expected_calibration_error > 0.8
    assert report.warnings


def test_calibration_requires_labels_and_authorization():
    with pytest.raises(ValueError, match="labelled"):
        calibration_report((), authorized=True)
    with pytest.raises(PermissionError):
        calibration_report((
            CalibrationExample("a", 0.5, True, "group", "2026"),
        ), authorized=False)


def test_calibration_rejects_duplicate_identity():
    example = CalibrationExample("a", 0.5, True, "group", "2026")
    with pytest.raises(ValueError, match="duplicate"):
        calibration_report((example, example), authorized=True)
