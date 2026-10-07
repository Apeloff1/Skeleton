from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.evaluation.firewall import (
    EvaluationFirewall,
    EvaluationFirewallError,
    EvaluationQueryReceipt,
    EvaluationSet,
    EvaluatorIdentity,
    PromotionEvidence,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EvaluationFirewallTests(unittest.TestCase):
    def firewall(self) -> EvaluationFirewall:
        firewall = EvaluationFirewall()
        firewall.register_set(
            EvaluationSet(
                set_id="dev-public",
                eval_class="development",
                content_digest=sha("dev"),
                population_id="general-code",
                query_budget=None,
                training_excluded=False,
            )
        )
        firewall.register_set(
            EvaluationSet(
                set_id="promotion-blind-v1",
                eval_class="promotion_holdout",
                content_digest=sha("blind"),
                population_id="general-code",
                query_budget=2,
                training_excluded=True,
            )
        )
        firewall.register_evaluator(
            EvaluatorIdentity(
                evaluator_id="eval-v1",
                implementation_digest=sha("evaluator-code"),
                policy_digest=sha("evaluation-policy"),
            )
        )
        return firewall

    def test_promotion_holdout_requires_training_exclusion_and_budget(self) -> None:
        with self.assertRaisesRegex(EvaluationFirewallError, "query budget"):
            EvaluationSet(
                set_id="bad",
                eval_class="promotion_holdout",
                content_digest=sha("bad"),
                population_id="code",
                query_budget=None,
                training_excluded=True,
            )
        with self.assertRaisesRegex(EvaluationFirewallError, "excluded from training"):
            EvaluationSet(
                set_id="bad2",
                eval_class="promotion_holdout",
                content_digest=sha("bad2"),
                population_id="code",
                query_budget=1,
                training_excluded=False,
            )

    def test_training_reference_to_holdout_fails_closed(self) -> None:
        firewall = self.firewall()
        with self.assertRaisesRegex(EvaluationFirewallError, "leaked"):
            firewall.assert_training_exclusion(("dataset:a", "promotion-blind-v1"))

    def test_holdout_query_budget_cannot_be_exceeded(self) -> None:
        firewall = self.firewall()
        firewall.query(
            candidate_id="candidate-a",
            set_id="promotion-blind-v1",
            evaluator_id="eval-v1",
            purpose="promotion",
        )
        firewall.query(
            candidate_id="candidate-a",
            set_id="promotion-blind-v1",
            evaluator_id="eval-v1",
            purpose="promotion",
        )
        with self.assertRaisesRegex(EvaluationFirewallError, "budget exhausted"):
            firewall.query(
                candidate_id="candidate-a",
                set_id="promotion-blind-v1",
                evaluator_id="eval-v1",
                purpose="hyperparameter-search",
            )

    def test_contaminated_holdout_cannot_justify_promotion(self) -> None:
        firewall = self.firewall()
        firewall.query(
            candidate_id="candidate-a",
            set_id="promotion-blind-v1",
            evaluator_id="eval-v1",
            purpose="promotion",
        )
        firewall.mark_contaminated(
            "promotion-blind-v1",
            reason="answers appeared in training corpus",
        )
        with self.assertRaisesRegex(EvaluationFirewallError, "contaminated"):
            firewall.promotion_evidence(
                candidate_id="candidate-a",
                holdout_set_id="promotion-blind-v1",
                evaluator_id="eval-v1",
            )

    def test_promotion_evidence_binds_set_and_evaluator_identity(self) -> None:
        firewall = self.firewall()
        first = firewall.query(
            candidate_id="candidate-b",
            set_id="promotion-blind-v1",
            evaluator_id="eval-v1",
            purpose="promotion",
        )
        evidence = firewall.promotion_evidence(
            candidate_id="candidate-b",
            holdout_set_id="promotion-blind-v1",
            evaluator_id="eval-v1",
        )
        self.assertEqual(evidence.query_receipt_digests, (first.digest,))
        self.assertEqual(evidence.holdout_queries_used, 1)
        self.assertEqual(evidence.holdout_query_budget, 2)
        self.assertEqual(len(evidence.digest), 64)

    def test_evaluator_identity_cannot_drift_in_place(self) -> None:
        firewall = self.firewall()
        with self.assertRaisesRegex(EvaluationFirewallError, "identity conflict"):
            firewall.register_evaluator(
                EvaluatorIdentity(
                    evaluator_id="eval-v1",
                    implementation_digest=sha("changed-code"),
                    policy_digest=sha("evaluation-policy"),
                )
            )

    def test_evaluation_metadata_is_structurally_immutable(self) -> None:
        metadata = {"sealed": True}
        evaluation_set = EvaluationSet(
            set_id="immutable-holdout",
            eval_class="promotion_holdout",
            content_digest=sha("immutable"),
            population_id="general-code",
            query_budget=1,
            training_excluded=True,
            metadata=metadata,
        )
        metadata["sealed"] = False
        self.assertTrue(evaluation_set.metadata["sealed"])
        with self.assertRaises(TypeError):
            evaluation_set.metadata["sealed"] = False  # type: ignore[index]

    def test_forged_query_receipt_index_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvaluationFirewallError, "positive integer"):
            EvaluationQueryReceipt(
                candidate_id="candidate",
                set_identity="evalset:" + sha("set"),
                evaluator_identity="evaluator:" + sha("evaluator"),
                query_index=0,
                purpose="promotion",
            )

    def test_promotion_evidence_is_non_authoritative_and_receipt_bound(self) -> None:
        receipt = sha("query-receipt")
        evidence = PromotionEvidence(
            candidate_id="candidate",
            holdout_set_identity="evalset:" + sha("set"),
            evaluator_identity="evaluator:" + sha("evaluator"),
            query_receipt_digests=(receipt,),
            holdout_queries_used=1,
            holdout_query_budget=2,
        )
        self.assertFalse(evidence.production_authority)
        self.assertFalse(evidence.direct_self_modify)
        self.assertEqual(evidence.query_receipt_digests, (receipt,))
        with self.assertRaisesRegex(EvaluationFirewallError, "match receipt lineage"):
            PromotionEvidence(
                candidate_id="candidate",
                holdout_set_identity="evalset:" + sha("set"),
                evaluator_identity="evaluator:" + sha("evaluator"),
                query_receipt_digests=(receipt,),
                holdout_queries_used=2,
                holdout_query_budget=2,
            )
        with self.assertRaisesRegex(EvaluationFirewallError, "production authority"):
            PromotionEvidence(
                candidate_id="candidate",
                holdout_set_identity="evalset:" + sha("set"),
                evaluator_identity="evaluator:" + sha("evaluator"),
                query_receipt_digests=(receipt,),
                holdout_queries_used=1,
                holdout_query_budget=2,
                production_authority=True,
            )


if __name__ == "__main__":
    unittest.main()
