"""Cross-facet temporal qualification: benchmark, chronology, uncertainty, authority."""
from __future__ import annotations

import unittest
from dataclasses import replace

from skeleton.ai.training.temporal_signals import TemporalSignalError
from skeleton.ai.training.temporal_benchmark import (
    TemporalCompetence, evaluate_temporal_competence, require_temporal_benchmark,
)
from skeleton.ai.training.temporal_invariants import (
    RegimeObservation, assess_regime_invariance, require_regime_invariance,
)
from skeleton.ai.training.temporal_uncertainty import (
    ResidualObservation, rolling_uncertainty_set, require_bounded_uncertainty,
)
from skeleton.ai.training.temporal_causality import (
    TemporalEvent, CausalEdge, validate_causal_chronology,
)
from skeleton.ai.training.temporal_abstention import (
    decide_temporal_authority, require_temporal_authorization,
)
from skeleton.ai.training.temporal_consistency import prove_temporal_consistency
from skeleton.ai.training.bitemporal_authority import BitemporalFact, bitemporal_snapshot
from skeleton.ai.training.temporal_provenance import ProvenanceNode, assess_source_independence

A, B, C, D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)


def chronology():
    cause = TemporalEvent("cause", "topic", 2020, A)
    effect = TemporalEvent("effect", "topic", 2025, B)
    return validate_causal_chronology(
        (cause, effect),
        (CausalEdge("cause-to-effect", cause.digest, effect.digest, "causal", C),),
    )


def calibration():
    return rolling_uncertainty_set(
        (ResidualObservation(f"sample-{i}", 2020 + i // 10, 100_000) for i in range(30)),
        max_window=32,
    )


def decision(*, roots=2, uncertainty=100_000):
    return decide_temporal_authority(
        subject="topic", policy_year=2025, authority_digest=D,
        support_ppm=900_000, opposition_ppm=0, uncertainty_ppm=uncertainty,
        regime_change_ppm=0, provenance_roots=roots,
    )


class TestTemporalQualification(unittest.TestCase):
    def test_benchmark_requires_lowercase_git_head_and_all_competence_floors(self):
        metrics = TemporalCompetence(900_000, 900_000, 950_000, 900_000, 900_000, 900_000)
        receipt = evaluate_temporal_competence(
            exact_head_commit="a" * 40, suite_digest=B, metrics=metrics,
        )
        self.assertTrue(receipt.passed)
        self.assertEqual(require_temporal_benchmark(receipt), receipt.digest)
        with self.assertRaisesRegex(TemporalSignalError, "exact head"):
            evaluate_temporal_competence(exact_head_commit="z" * 40, suite_digest=B, metrics=metrics)
        poor = TemporalCompetence(500_000, 900_000, 900_000, 900_000, 900_000, 900_000)
        with self.assertRaisesRegex(TemporalSignalError, "failed"):
            require_temporal_benchmark(
                evaluate_temporal_competence(
                    exact_head_commit="b" * 64, suite_digest=B, metrics=poor,
                )
            )

    def test_regime_transfer_detects_changed_mechanism_and_bool_scores(self):
        a = RegimeObservation("era-1", "topic", A, 900_000, C)
        b = RegimeObservation("era-2", "topic", A, 850_000, D)
        receipt = assess_regime_invariance((a, b))
        self.assertTrue(receipt.invariant)
        self.assertEqual(require_regime_invariance(receipt), receipt.digest)
        different = RegimeObservation("era-2", "topic", B, 900_000, D)
        with self.assertRaisesRegex(TemporalSignalError, "invariantly"):
            require_regime_invariance(assess_regime_invariance((a, different)))
        with self.assertRaisesRegex(TemporalSignalError, "support"):
            replace(a, support_ppm=True)

    def test_generator_calibration_is_consumed_once_and_bounds_uncertainty(self):
        receipt = calibration()
        self.assertEqual(receipt.sample_count, 30)
        self.assertEqual(receipt.radius_ppm, 100_000)
        self.assertEqual(require_bounded_uncertainty(receipt), receipt.digest)
        with self.assertRaisesRegex(TemporalSignalError, "window"):
            rolling_uncertainty_set((ResidualObservation("x", 2026, 100),), max_window=0)
        with self.assertRaisesRegex(TemporalSignalError, "insufficient"):
            require_bounded_uncertainty(
                rolling_uncertainty_set((ResidualObservation("x", 2026, 100),))
            )

    def test_chronology_validates_ids_future_causes_and_cycles(self):
        self.assertEqual(chronology().causal_edge_count, 1)
        early = TemporalEvent("first", "topic", 2020, A)
        late = TemporalEvent("second", "topic", 2021, B)
        with self.assertRaisesRegex(TemporalSignalError, "after effect"):
            validate_causal_chronology(
                (early, late),
                (CausalEdge("reverse", late.digest, early.digest, "causal", C),),
            )
        with self.assertRaisesRegex(TemporalSignalError, "duplicate causal edge"):
            edge = CausalEdge("repeated", early.digest, late.digest, "causal", C)
            validate_causal_chronology((early, late), (edge, edge))
        same_year_a = TemporalEvent("a", "topic", 2020, A)
        same_year_b = TemporalEvent("b", "topic", 2020, B)
        with self.assertRaisesRegex(TemporalSignalError, "cycle"):
            validate_causal_chronology(
                (same_year_a, same_year_b),
                (
                    CausalEdge("ab", same_year_a.digest, same_year_b.digest, "causal", C),
                    CausalEdge("ba", same_year_b.digest, same_year_a.digest, "causal", D),
                ),
            )

    def test_abstention_requires_independent_evidence_and_calibration(self):
        self.assertEqual(require_temporal_authorization(decision()), decision().digest)
        with self.assertRaisesRegex(TemporalSignalError, "did not authorize"):
            require_temporal_authorization(decision(roots=1))
        with self.assertRaisesRegex(TemporalSignalError, "did not authorize"):
            require_temporal_authorization(decision(uncertainty=350_000))
        with self.assertRaisesRegex(TemporalSignalError, "invalid support"):
            decide_temporal_authority(
                subject="topic", policy_year=2025, authority_digest=D,
                support_ppm=True, opposition_ppm=0, uncertainty_ppm=0,
                regime_change_ppm=0, provenance_roots=2,
            )

    def test_consistency_proof_is_bound_to_bitemporal_cutoff_and_provenance(self):
        fact = BitemporalFact("f", "topic", "has", A, 2020, 2030, 2020, 2050, B)
        historical = bitemporal_snapshot((fact,), world_year=2025, knowledge_year=2025)
        independent = assess_source_independence((ProvenanceNode(A), ProvenanceNode(B)))
        proof = prove_temporal_consistency(
            subject="topic", policy_year=2025,
            bitemporal_snapshot=historical, independence_receipt=independent,
            chronology_receipt=chronology(), uncertainty_receipt=calibration(),
            decision=decision(),
        )
        self.assertTrue(proof.consistent)
        self.assertEqual(len(proof.digest), 64)
        future = bitemporal_snapshot((fact,), world_year=2025, knowledge_year=2026)
        with self.assertRaisesRegex(TemporalSignalError, "knowledge snapshot"):
            prove_temporal_consistency(
                subject="topic", policy_year=2025, bitemporal_snapshot=future,
                independence_receipt=independent, chronology_receipt=chronology(),
                uncertainty_receipt=calibration(), decision=decision(),
            )
        with self.assertRaisesRegex(TemporalSignalError, "not authorized"):
            prove_temporal_consistency(
                subject="topic", policy_year=2025, bitemporal_snapshot=historical,
                independence_receipt=independent, chronology_receipt=chronology(),
                uncertainty_receipt=calibration(), decision=decision(roots=1),
            )

    def test_cross_subject_and_unbounded_error_are_not_certified(self):
        a = RegimeObservation("era-1", "a", A, 950_000, B)
        b = RegimeObservation("era-2", "b", A, 950_000, C)
        with self.assertRaisesRegex(TemporalSignalError, "cross-subject"):
            assess_regime_invariance((a, b))
        with self.assertRaisesRegex(TemporalSignalError, "radius"):
            require_bounded_uncertainty(
                rolling_uncertainty_set(
                    ResidualObservation(str(i), 2026, 500_000) for i in range(30)
                )
            )


if __name__ == "__main__":
    unittest.main()
