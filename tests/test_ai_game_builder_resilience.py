from __future__ import annotations

import pytest

from skeleton.ai.game_builder.contracts import EvaluatorProvenance, canonical_digest
from skeleton.ai.game_builder.resilience import (
    DissentLedger,
    ImpactGraph,
    Invariant,
    InvariantRegistry,
    NoveltyRecord,
    NoveltyReservoir,
    Objection,
    ResilienceError,
)


def _authority(
    evaluator_id: str,
    *evidence_refs: str,
) -> EvaluatorProvenance:
    return EvaluatorProvenance(
        evaluator_id=evaluator_id,
        operation_id=f"operation:{evaluator_id}",
        execution_id=f"execution:{evaluator_id}",
        execution_identity_digest=canonical_digest({"execution": evaluator_id}),
        finalization_intent_digest=canonical_digest({"finalization": evaluator_id}),
        authority_kind="deterministic_control",
        authority_identity_digest=canonical_digest({"authority": evaluator_id}),
        method_id="resilience-assurance",
        source_revision=canonical_digest({"source": evaluator_id})[:40],
        output_evidence_refs=tuple(evidence_refs),
    )


def _novelty(digest: str, quality: float, x: float, y: float) -> NoveltyRecord:
    return NoveltyRecord.create(
        candidate_digest=digest,
        quality_score=quality,
        features={"x": x, "y": y},
    )


def test_novelty_reservoir_rejects_weaker_near_duplicate_and_replaces_with_stronger() -> None:
    reservoir = NoveltyReservoir(capacity=4, minimum_distance=0.10)
    first = _novelty("a" * 64, 0.60, 0.10, 0.10)
    weaker = _novelty("b" * 64, 0.50, 0.11, 0.10)
    stronger = _novelty("c" * 64, 0.90, 0.11, 0.10)

    assert reservoir.admit(first) is True
    assert reservoir.admit(weaker) is False
    assert [row.candidate_digest for row in reservoir.records] == ["a" * 64]

    assert reservoir.admit(stronger) is True
    assert [row.candidate_digest for row in reservoir.records] == ["c" * 64]


def test_novelty_identity_reuse_with_changed_payload_fails_closed() -> None:
    reservoir = NoveltyReservoir()
    original = _novelty("d" * 64, 0.70, 0.20, 0.20)
    changed = _novelty("d" * 64, 0.80, 0.30, 0.30)
    assert reservoir.admit(original) is True

    with pytest.raises(ResilienceError, match="identity reused"):
        reservoir.admit(changed)


def test_dissent_ledger_preserves_blocker_until_explicit_resolution() -> None:
    ledger = DissentLedger()
    objection = Objection(
        objection_id="OBJ-1",
        artifact_digest="1" * 64,
        evidence_digest="2" * 64,
        summary="Continuity break survives local improvement.",
        severity=8,
        authority_provenance=_authority("dissent-authority", "2" * 64),
        dependency_ids=("canon:chapter-2",),
    )
    ledger.add(objection)

    assert [row.objection_id for row in ledger.blockers_for(artifact_digest="1" * 64)] == ["OBJ-1"]
    assert [
        row.objection_id
        for row in ledger.blockers_for(
            artifact_digest="9" * 64,
            changed_dependency_ids=("canon:chapter-2",),
        )
    ] == ["OBJ-1"]

    ledger.resolve(
        "OBJ-1",
        resolution_digest="3" * 64,
        resolution_authority=_authority("independent-resolver", "3" * 64),
    )
    assert ledger.blockers_for(artifact_digest="1" * 64) == ()
    assert ledger.snapshot()["items"][0]["resolved_by_digest"] == "3" * 64


def test_dissent_rejects_unattributed_objection_evidence() -> None:
    with pytest.raises(ResilienceError, match="referenced by dissent authority"):
        Objection(
            objection_id="OBJ-UNBOUND",
            artifact_digest="1" * 64,
            evidence_digest="2" * 64,
            summary="Unattributed evidence.",
            severity=4,
            authority_provenance=_authority("wrong-dissent-authority", "9" * 64),
        )


def test_critical_dissent_requires_independent_resolution_authority() -> None:
    ledger = DissentLedger()
    objection = Objection(
        objection_id="OBJ-CRITICAL",
        artifact_digest="1" * 64,
        evidence_digest="2" * 64,
        summary="Critical blocker.",
        severity=8,
        authority_provenance=_authority("same-authority", "2" * 64),
    )
    ledger.add(objection)
    with pytest.raises(
        ResilienceError,
        match="critical objection resolution requires independent authority",
    ):
        ledger.resolve(
            "OBJ-CRITICAL",
            resolution_digest="3" * 64,
            resolution_authority=_authority("same-authority", "3" * 64),
        )


def test_impact_calibration_receipt_binds_observed_evidence() -> None:
    evidence = "impact-evidence-" + "e" * 32
    authority = _authority("impact-calibrator", evidence)
    receipt = ImpactGraph.calibration_receipt(
        ("project", "scene"),
        ("project", "quest"),
        evaluator_provenance=authority,
        evidence_digest=evidence,
    )
    assert receipt.precision == 0.5
    assert receipt.recall == 0.5
    assert canonical_digest(receipt.payload()) == receipt.receipt_digest

    with pytest.raises(ResilienceError, match="referenced by evaluator authority"):
        ImpactGraph.calibration_receipt(
            ("project",),
            ("project",),
            evaluator_provenance=_authority("wrong-impact-calibrator", "other-" + "x" * 32),
            evidence_digest=evidence,
        )


def test_impact_calibration_receipt_rejects_self_consistent_false_scores() -> None:
    evidence = "impact-evidence-" + "e" * 32
    authority = _authority("impact-calibrator", evidence)
    payload = {
        "evaluator_provenance_digest": authority.digest,
        "evidence_digest": evidence,
        "observed_ids": ["project", "quest"],
        "precision": 1.0,
        "predicted_ids": ["project", "scene"],
        "recall": 1.0,
    }
    with pytest.raises(
        ResilienceError,
        match="precision does not match recorded sets",
    ):
        from skeleton.ai.game_builder.resilience import ImpactCalibrationReceipt

        ImpactCalibrationReceipt(
            predicted_ids=("project", "scene"),
            observed_ids=("project", "quest"),
            precision=1.0,
            recall=1.0,
            evaluator_provenance=authority,
            evidence_digest=evidence,
            receipt_digest=canonical_digest(payload),
        )


def test_impact_graph_computes_transitive_blast_radius_and_rejects_unknown_dependency() -> None:
    graph = ImpactGraph()
    graph.add_node("project")
    graph.add_node("scene", depends_on=("project",))
    graph.add_node("quest", depends_on=("scene",))
    graph.add_node("ui", depends_on=("project",))

    assert graph.blast_radius(("project",)) == ("project", "quest", "scene", "ui")
    assert graph.blast_radius(("scene",)) == ("quest", "scene")
    assert graph.calibration(("project", "scene"), ("project", "quest")) == {
        "precision": 0.5,
        "recall": 0.5,
    }

    with pytest.raises(ResilienceError, match="unknown impact dependencies"):
        graph.add_node("bad", depends_on=("missing",))


def test_invariant_registry_rejects_cross_pillar_duplicate_and_is_order_stable() -> None:
    left = InvariantRegistry()
    right = InvariantRegistry()

    a = Invariant(
        invariant_id="INV-A",
        scope="combat",
        expression="health >= 0",
        source_pillar="mechanics",
        severity=8,
        inherited_by=("boss",),
    )
    b = Invariant(
        invariant_id="INV-B",
        scope="narrative",
        expression="knowledge <= observed_events",
        source_pillar="canon",
        severity=8,
    )

    left.add(a)
    left.add(b)
    right.add(b)
    right.add(a)

    assert left.digest() == right.digest()
    assert [item.invariant_id for item in left.applicable("boss")] == ["INV-A", "INV-B"]
    assert [item.invariant_id for item in left.applicable("npc")] == ["INV-B"]

    with pytest.raises(ResilienceError, match="ambiguous duplicate invariant"):
        left.add(
            Invariant(
                invariant_id="INV-C",
                scope="combat",
                expression="health >= 0",
                source_pillar="narrative",
                severity=8,
            )
        )
