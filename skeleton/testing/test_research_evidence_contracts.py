"""Adversarial identity and numeric-boundary tests for research evidence."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.research.evidence_contracts import (
    EvidenceGraph,
    EvidenceNode,
    ExperimentPlan,
    Outcome,
    ReproductionRecord,
    ResearchConclusion,
    ResearchError,
    ResearchQuestion,
    synthesize,
    validate_reproduction,
)


class ResearchEvidenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.node = EvidenceNode(
            evidence_id="e1",
            source_id="source-1",
            source_digest="a" * 64,
            method="bounded-reproduction",
            claim_ids=("claim-1",),
            outcome=Outcome.SUPPORTS,
        )
        self.plan = ExperimentPlan(
            experiment_id="exp-1",
            hypothesis="Evidence predicts a bounded measurable outcome",
            metrics=("accuracy",),
            decision_rule="accuracy >= 0.9",
            max_trials=3,
        )
        self.record = ReproductionRecord(
            reproduction_id="run-1",
            evidence_digest=self.node.digest,
            experiment_digest=self.plan.digest,
            metrics=(("accuracy", 0.95),),
            outcome=Outcome.SUPPORTS,
            trials=2,
        )

    def test_valid_reproduction_binds_exact_evidence_and_plan(self) -> None:
        validate_reproduction(self.node, self.plan, self.record)
        self.assertEqual(len(self.node.digest), 64)
        self.assertEqual(len(self.record.digest), 64)

    def test_source_identity_is_restricted_to_canonical_sha256(self) -> None:
        for invalid in ("", "not-a-digest", "A" * 64, "g" * 64, "a" * 63, "a" * 65):
            with self.subTest(invalid=invalid), self.assertRaises(ResearchError):
                replace(self.node, source_digest=invalid)

    def test_reproduction_rejects_unbound_digest_shapes(self) -> None:
        for name in ("evidence_digest", "experiment_digest"):
            for invalid in ("", "f" * 63, "F" * 64, "z" * 64):
                with self.subTest(name=name, invalid=invalid), self.assertRaises(ResearchError):
                    replace(self.record, **{name: invalid})

    def test_conclusion_rejects_invalid_evidence_identity(self) -> None:
        with self.assertRaises(ResearchError):
            ResearchConclusion(
                conclusion_id="conclusion-1",
                question_id="question-1",
                claim_id="claim-1",
                evidence_digests=("noncanonical",),
                outcomes=(Outcome.SUPPORTS,),
                conclusion="A conclusion",
                limitations=("single source",),
            )

    def test_overflowing_and_nonfinite_metrics_are_rejected(self) -> None:
        for value in (10 ** 1000, float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ResearchError):
                replace(self.record, metrics=(("accuracy", value),))

    def test_reproduction_enforces_boundaries_after_canonicalization(self) -> None:
        with self.assertRaises(ResearchError):
            validate_reproduction(self.node, self.plan, replace(self.record, trials=4))
        with self.assertRaises(ResearchError):
            validate_reproduction(self.node, self.plan, replace(self.record, metrics=(("recall", 0.95),)))
        different_node = replace(self.node, evidence_id="e2")
        with self.assertRaises(ResearchError):
            validate_reproduction(different_node, self.plan, self.record)

    def test_negative_evidence_remains_visible_in_conclusion(self) -> None:
        graph = EvidenceGraph()
        node = replace(self.node, outcome=Outcome.NEGATIVE)
        graph.add(node)
        result = synthesize(
            ResearchQuestion(
                question_id="question-1",
                question="Does the intervention improve outcomes?",
                scope="bounded pilot",
                limitations=("pilot size",),
            ),
            "claim-1",
            graph,
            "No demonstrated effect",
            (),
        )
        self.assertEqual(result.evidence_digests, (node.digest,))
        self.assertIn("conflicting_or_negative_evidence", result.limitations)


if __name__ == "__main__":
    unittest.main()
