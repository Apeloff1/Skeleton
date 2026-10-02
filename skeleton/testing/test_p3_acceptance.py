from __future__ import annotations

import unittest

from skeleton.eval.p3_acceptance import (
    AutonomousWorkerScenario,
    P3AcceptanceError,
    P3AcceptanceHarness,
    ResearchAcceptanceCase,
    ResearchClaim,
    SOTACandidateCase,
)


class P3AcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = P3AcceptanceHarness()

    def test_autonomous_worker_accepts_bounded_recoverable_long_horizon_case(self) -> None:
        receipt = self.harness.accept_autonomous_worker(
            AutonomousWorkerScenario(
                objective_id="objective:p3-worker",
                budget_limit=100,
                budget_spent=64,
                delegated_authority=("repo:read", "repo:bounded-write"),
                checkpoint_refs=("checkpoint:1", "checkpoint:2", "checkpoint:3"),
                override_ref="override:human-stop",
                recovery_ref="recovery:checkpoint-2",
                stress_conditions=frozenset(
                    {
                        "interruption",
                        "stale_work",
                        "conflict",
                        "deadline",
                        "resource_exhaustion",
                    }
                ),
            )
        )
        self.assertEqual(receipt.budget_headroom, 36)
        self.assertEqual(len(receipt.receipt_digest), 64)

    def test_autonomous_worker_rejects_budget_leakage(self) -> None:
        with self.assertRaisesRegex(P3AcceptanceError, "exceeded declared budget"):
            self.harness.accept_autonomous_worker(
                AutonomousWorkerScenario(
                    objective_id="objective:bad",
                    budget_limit=10,
                    budget_spent=11,
                    delegated_authority=("repo:read",),
                    checkpoint_refs=("checkpoint:1", "checkpoint:2"),
                    override_ref="override:stop",
                    recovery_ref="recovery:1",
                    stress_conditions=frozenset(
                        {
                            "interruption",
                            "stale_work",
                            "conflict",
                            "deadline",
                            "resource_exhaustion",
                        }
                    ),
                )
            )

    def test_research_acceptance_requires_claim_evidence_and_independent_review(self) -> None:
        receipt = self.harness.accept_research(
            ResearchAcceptanceCase(
                question_id="research:p3",
                claims=(
                    ResearchClaim("claim:1", ("source:a", "source:b")),
                    ResearchClaim("claim:2", ("source:c",)),
                ),
                contradiction_refs=("contradiction:resolved",),
                reproduction_refs=("repro:run-1", "repro:run-2"),
                uncertainty_ref="uncertainty:bootstrap-ci",
                negative_result_refs=("negative:null-result",),
                implementer_id="researcher:primary",
                reviewer_id="reviewer:independent",
            )
        )
        self.assertEqual(receipt.claim_count, 2)
        self.assertEqual(receipt.evidence_ref_count, 3)

    def test_research_self_review_is_rejected(self) -> None:
        with self.assertRaisesRegex(P3AcceptanceError, "independent review"):
            self.harness.accept_research(
                ResearchAcceptanceCase(
                    question_id="research:p3",
                    claims=(ResearchClaim("claim:1", ("source:a",)),),
                    contradiction_refs=("contradiction:1",),
                    reproduction_refs=("repro:1",),
                    uncertainty_ref="uncertainty:1",
                    negative_result_refs=("negative:1",),
                    implementer_id="same",
                    reviewer_id="same",
                )
            )

    def test_sota_candidate_is_bounded_and_independently_replayed(self) -> None:
        receipt = self.harness.qualify_sota_candidate(
            SOTACandidateCase(
                benchmark_id="benchmark:heldout-v1",
                task_scope="repository-repair",
                population="heldout-fixtures-v1",
                baseline_metrics={"quality": 0.80, "robustness": 0.75},
                candidate_metrics={"quality": 0.84, "robustness": 0.76},
                contamination_audit_refs=("contamination:audit-1",),
                replay_refs=("replay:independent-1", "replay:independent-2"),
                robustness_refs=("robustness:red-team",),
                security_refs=("security:adversarial",),
                latency_ms=125.0,
                cost_per_case=0.0,
                implementer_id="builder",
                verifier_id="independent-verifier",
            )
        )
        self.assertEqual(receipt.claim, "bounded_sota_candidate")
        self.assertEqual(receipt.task_scope, "repository-repair")
        self.assertEqual(len(receipt.qualification_digest), 64)

    def test_sota_candidate_rejects_contamination_shortcut(self) -> None:
        with self.assertRaisesRegex(P3AcceptanceError, "contamination audit"):
            self.harness.qualify_sota_candidate(
                SOTACandidateCase(
                    benchmark_id="benchmark:x",
                    task_scope="scope:x",
                    population="population:x",
                    baseline_metrics={"quality": 0.8},
                    candidate_metrics={"quality": 0.9},
                    contamination_audit_refs=("audit:missing-prefix",),
                    replay_refs=("replay:1",),
                    robustness_refs=("robustness:1",),
                    security_refs=("security:1",),
                    latency_ms=1.0,
                    cost_per_case=0.0,
                    implementer_id="impl",
                    verifier_id="verify",
                )
            )


if __name__ == "__main__":
    unittest.main()
