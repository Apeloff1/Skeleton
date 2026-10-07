import unittest

from skeleton.ai.model_runtime import (
    NativeLLMRuntime,
    RuntimeContractError,
    admit_promoted_candidate,
)
from skeleton.ai.model_runtime.runtime_checkpoint import portable_model_snapshot, snapshot_digest
from skeleton.ai.training.flgb_training_runtime import CandidateWeights, PromotionEvidence
from skeleton.cortex.transformer import TinyTransformer


D = "a" * 64


class TestGovernedTrainingAdmission(unittest.TestCase):
    def runtime(self):
        model = TinyTransformer(vocab=["<unk>", "a", "b"], dim=4, ctx=8, n_heads=1, n_layers=1, d_ff=8)
        return NativeLLMRuntime(model)

    def evidence(self, candidate, **overrides):
        values = dict(
            candidate_digest=candidate.digest,
            exact_head_commit=D,
            rights_digest=D,
            contamination_scan_digest=D,
            evaluation_digest=D,
            rollback_digest=D,
            independent_verifier="independent",
            rights_passed=True,
            contamination_clear=True,
            evaluation_passed=True,
            rollback_ready=True,
        )
        values.update(overrides)
        return PromotionEvidence(**values)

    def promoted_candidate_for_mutated_runtime(self, runtime):
        base = runtime.model_digest
        runtime.model.bout[0] += 0.25
        weights = snapshot_digest(portable_model_snapshot(runtime.model))
        return CandidateWeights("candidate", weights, D, base, "promoted")

    def test_exact_promoted_candidate_is_atomically_admitted(self):
        runtime = self.runtime()
        prior = runtime.model_digest
        candidate = self.promoted_candidate_for_mutated_runtime(runtime)
        receipt = admit_promoted_candidate(runtime, candidate, self.evidence(candidate))
        self.assertEqual(receipt.prior_model_digest, prior)
        self.assertEqual(receipt.admitted_model_digest, candidate.weights_digest)
        self.assertEqual(runtime.model_digest, candidate.weights_digest)
        self.assertEqual(receipt.candidate_digest, candidate.digest)

    def test_candidate_only_status_cannot_enter_runtime(self):
        runtime = self.runtime()
        base = runtime.model_digest
        runtime.model.bout[0] += 0.25
        weights = snapshot_digest(portable_model_snapshot(runtime.model))
        candidate = CandidateWeights("candidate", weights, D, base, "candidate")
        with self.assertRaises(RuntimeContractError):
            admit_promoted_candidate(runtime, candidate, self.evidence(candidate))
        self.assertEqual(runtime.model_digest, base)

    def test_failed_independent_gate_cannot_enter_runtime(self):
        runtime = self.runtime()
        base = runtime.model_digest
        candidate = self.promoted_candidate_for_mutated_runtime(runtime)
        evidence = self.evidence(candidate, contamination_clear=False)
        with self.assertRaises(RuntimeContractError):
            admit_promoted_candidate(runtime, candidate, evidence)
        self.assertEqual(runtime.model_digest, base)

    def test_candidate_digest_mismatch_fails_closed(self):
        runtime = self.runtime()
        base = runtime.model_digest
        candidate = self.promoted_candidate_for_mutated_runtime(runtime)
        evidence = PromotionEvidence(
            D, D, D, D, D, D, "independent", True, True, True, True
        )
        with self.assertRaises(RuntimeContractError):
            admit_promoted_candidate(runtime, candidate, evidence)
        self.assertEqual(runtime.model_digest, base)

    def test_wrong_base_model_cannot_be_admitted(self):
        runtime = self.runtime()
        base = runtime.model_digest
        runtime.model.bout[0] += 0.25
        weights = snapshot_digest(portable_model_snapshot(runtime.model))
        candidate = CandidateWeights("candidate", weights, D, D, "promoted")
        with self.assertRaises(RuntimeContractError):
            admit_promoted_candidate(runtime, candidate, self.evidence(candidate))
        self.assertEqual(runtime.model_digest, base)

    def test_declared_weights_must_match_mutated_model(self):
        runtime = self.runtime()
        base = runtime.model_digest
        runtime.model.bout[0] += 0.25
        candidate = CandidateWeights("candidate", D, D, base, "promoted")
        with self.assertRaises(RuntimeContractError):
            admit_promoted_candidate(runtime, candidate, self.evidence(candidate))
        self.assertEqual(runtime.model_digest, base)

    def test_unchanged_weights_are_not_a_candidate_update(self):
        runtime = self.runtime()
        base = runtime.model_digest
        candidate = CandidateWeights("candidate", base, D, base, "promoted")
        with self.assertRaises(RuntimeContractError):
            admit_promoted_candidate(runtime, candidate, self.evidence(candidate))
        self.assertEqual(runtime.model_digest, base)


if __name__ == "__main__":
    unittest.main()
