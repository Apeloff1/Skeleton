"""Exact-head, evidence-bound temporal certification and candidate-only admission."""
from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from skeleton.ai.training.temporal_signals import TemporalSignalError
from skeleton.ai.training.temporal_benchmark import TemporalCompetence, evaluate_temporal_competence
from skeleton.ai.training.temporal_intelligence import TemporalAuthorityReceipt
from skeleton.ai.training.temporal_provenance import ProvenanceNode, assess_source_independence
from skeleton.ai.training.temporal_uncertainty import ResidualObservation, rolling_uncertainty_set
from skeleton.ai.training.temporal_ensemble import DriftDetectorVote, combine_drift_votes
from skeleton.ai.training.temporal_causality import TemporalEvent, CausalEdge, validate_causal_chronology
from skeleton.ai.training.temporal_invariants import RegimeObservation, assess_regime_invariance
from skeleton.ai.training.temporal_facts import TemporalFact, snapshot_facts
from skeleton.ai.training.temporal_abstention import decide_temporal_authority
from skeleton.ai.training.temporal_certificate import issue_temporal_certificate
from skeleton.ai.training.temporal_certificate_registry import CertificateRegistration, CertificateRegistry
from skeleton.ai.training.temporal_learning_control import (
    LearningTemporalPolicy, decide_learning_disposition, require_weight_eligibility,
)
from skeleton.ai.training.temporal_admission import admit_temporal_training
from skeleton.ai.training.temporal_promotion import bind_temporal_promotion, require_temporal_promotion

A, B, C, D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
HEAD = "a" * 40


def evidence():
    authority = TemporalAuthorityReceipt("topic", 2025, A, B, 950_000, 900_000, 100_000, 0, True)
    benchmark = evaluate_temporal_competence(
        exact_head_commit=HEAD, suite_digest=B,
        metrics=TemporalCompetence(900_000, 900_000, 900_000, 900_000, 900_000, 900_000),
    )
    provenance = assess_source_independence((ProvenanceNode(A), ProvenanceNode(B)))
    uncertainty = rolling_uncertainty_set(
        ResidualObservation(f"sample-{i}", 2020 + i // 10, 100_000)
        for i in range(30)
    )
    drift = combine_drift_votes((
        DriftDetectorVote("adaptive", "adaptive-window", A, 100_000, 2020),
        DriftDetectorVote("distribution", "distribution", B, 200_000, 2020),
    ))
    cause = TemporalEvent("cause", "topic", 2020, A)
    effect = TemporalEvent("effect", "topic", 2025, B)
    chronology = validate_causal_chronology(
        (cause, effect), (CausalEdge("edge", cause.digest, effect.digest, "causal", C),),
    )
    invariance = assess_regime_invariance((
        RegimeObservation("era-1", "topic", A, 900_000, C),
        RegimeObservation("era-2", "topic", A, 900_000, D),
    ))
    historical = snapshot_facts((TemporalFact("fact", "topic", "has", A, 2020, 2030, 2020, B),), as_of_year=2025)
    decision = decide_temporal_authority(
        subject="topic", policy_year=2025, authority_digest=authority.digest,
        support_ppm=900_000, opposition_ppm=0, uncertainty_ppm=100_000,
        regime_change_ppm=0, provenance_roots=2,
    )
    return dict(
        subject="topic", policy_year=2025, exact_head_commit=HEAD,
        authority=authority, benchmark=benchmark, provenance=provenance,
        uncertainty=uncertainty, drift=drift, causality=chronology,
        invariance=invariance, historical_snapshot=historical, decision=decision,
    )


class TestTemporalCertificateAdmission(unittest.TestCase):
    def test_exact_head_certificate_to_candidate_only_training(self):
        proofs = evidence()
        certificate = issue_temporal_certificate(**proofs)
        registry = CertificateRegistry().register(
            CertificateRegistration(certificate.digest, "topic", 2025, 2026, 0)
        )
        policy = LearningTemporalPolicy("policy", "topic", 2025, 3, 300_000)
        learning = decide_learning_disposition(
            policy=policy, certificate=certificate, content_digest=C,
            stability_years=4, volatility_ppm=100_000,
        )
        self.assertEqual(learning.disposition, "weight-eligible")
        self.assertEqual(require_weight_eligibility(learning), learning.digest)
        admitted = admit_temporal_training(
            admission_id="candidate-001", content_digest=C, decision=learning,
            certificate=certificate, registry=registry, exact_head_commit=HEAD,
            base_model_digest=A, dataset_digest=B, authority_id="reviewer", epoch=1,
        )
        self.assertEqual(admitted.content_digest, C)
        self.assertEqual(admitted.certificate_digest, certificate.digest)
        self.assertEqual(len(admitted.digest), 64)

    def test_learning_admission_cannot_launder_different_content(self):
        proofs = evidence()
        cert = issue_temporal_certificate(**proofs)
        registry = CertificateRegistry().register(
            CertificateRegistration(cert.digest, "topic", 2025, 2026, 0)
        )
        decision = decide_learning_disposition(
            policy=LearningTemporalPolicy("policy", "topic", 2025, 3, 300_000),
            certificate=cert, content_digest=C, stability_years=4, volatility_ppm=100_000,
        )
        args = dict(
            admission_id="candidate", decision=decision, certificate=cert,
            registry=registry, exact_head_commit=HEAD, base_model_digest=A,
            dataset_digest=B, authority_id="reviewer", epoch=1,
        )
        with self.assertRaisesRegex(TemporalSignalError, "content identity mismatch"):
            admit_temporal_training(content_digest=D, **args)
        with self.assertRaisesRegex(TemporalSignalError, "exact-head mismatch"):
            admit_temporal_training(content_digest=C, **{**args, "exact_head_commit": "b" * 40})
        with self.assertRaisesRegex(TemporalSignalError, "admission epoch"):
            admit_temporal_training(content_digest=C, **{**args, "epoch": True})

    def test_certificate_rejects_unbound_authority_and_future_historical_cutoff(self):
        args = evidence()
        not_bound = dict(args, decision=replace(args["decision"], authority_digest=D))
        with self.assertRaisesRegex(TemporalSignalError, "decision authority mismatch"):
            issue_temporal_certificate(**not_bound)
        wrong_cutoff = dict(args, historical_snapshot=replace(args["historical_snapshot"], as_of_year=2026))
        with self.assertRaisesRegex(TemporalSignalError, "snapshot policy-year"):
            issue_temporal_certificate(**wrong_cutoff)

    def test_drift_disagreement_blocks_certificate_issue(self):
        args = evidence()
        changed = dict(args, drift=combine_drift_votes((
            DriftDetectorVote("adaptive", "adaptive-window", A, 10_000, 2020),
            DriftDetectorVote("distribution", "distribution", B, 900_000, 2020),
        )))
        with self.assertRaisesRegex(TemporalSignalError, "regime unstable"):
            issue_temporal_certificate(**changed)

    def test_registry_blocks_future_use_expiry_replay_and_cross_subject_supersession(self):
        cert = issue_temporal_certificate(**evidence())
        registered = CertificateRegistration(cert.digest, "topic", 2025, 2026, 0)
        registry = CertificateRegistry().register(registered)
        with self.assertRaisesRegex(TemporalSignalError, "not yet issued"):
            registry.require_active(cert.digest, policy_year=2024)
        with self.assertRaisesRegex(TemporalSignalError, "expired"):
            registry.require_active(cert.digest, policy_year=2027)
        with self.assertRaisesRegex(TemporalSignalError, "replay"):
            registry.register(registered)
        with self.assertRaisesRegex(TemporalSignalError, "supersession chronology"):
            registry.register(CertificateRegistration(D, "other", 2026, 2027, 1, cert.digest))
        with self.assertRaisesRegex(TemporalSignalError, "certificate sequence"):
            registry.register(CertificateRegistration(D, "topic", 2026, 2027, 3))

    def test_learning_policy_stays_retrieval_only_during_volatility(self):
        cert = issue_temporal_certificate(**evidence())
        policy = LearningTemporalPolicy("policy", "topic", 2025, 3, 200_000)
        decision = decide_learning_disposition(
            policy=policy, certificate=cert, content_digest=C,
            stability_years=1, volatility_ppm=500_000,
        )
        self.assertEqual(decision.disposition, "retrieval-only")
        with self.assertRaisesRegex(TemporalSignalError, "not temporally eligible"):
            require_weight_eligibility(decision)
        with self.assertRaisesRegex(TemporalSignalError, "weight eligibility"):
            replace(decision, disposition="weight-eligible")

    def test_promotion_binding_preserves_exact_head_and_independent_authority(self):
        authority = evidence()["authority"]
        candidate = SimpleNamespace(digest=A)
        promotion = SimpleNamespace(candidate_digest=A, qualified=True, digest=B, exact_head_commit=HEAD)
        qualification = SimpleNamespace(qualified=True, temporal_authority_digest=authority.digest, digest=C)
        binding = bind_temporal_promotion(candidate, promotion, qualification, authority, policy_year=2025)
        self.assertEqual(require_temporal_promotion(binding, candidate_digest=A, promotion_digest=B, exact_head_commit=HEAD), binding.digest)
        with self.assertRaisesRegex(TemporalSignalError, "exact-head mismatch"):
            require_temporal_promotion(binding, candidate_digest=A, promotion_digest=B, exact_head_commit="b" * 40)
        with self.assertRaisesRegex(TemporalSignalError, "temporal promotion candidate mismatch"):
            bind_temporal_promotion(candidate, replace_binding(promotion, candidate_digest=D), qualification, authority, policy_year=2025)


def replace_binding(item, **kwargs):
    return SimpleNamespace(**{**item.__dict__, **kwargs})


if __name__ == "__main__":
    unittest.main()
