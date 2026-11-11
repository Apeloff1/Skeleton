"""VOL-249 executable regression coverage: source-bound competing hypotheses."""
from __future__ import annotations

from dataclasses import replace
import math
import unittest

from skeleton.ai.research.hypothesis_engine import (
    EvidenceDirection, EvidenceMode, Hypothesis, HypothesisError,
    HypothesisEvidence, HypothesisLedger,
)
from skeleton.ai.research.source_lineage import ResearchSourceRegistry, SourceStatus


def _source(reg: ResearchSourceRegistry, name: str) -> str:
    reg.ingest(
        source_id=name,
        uri="https://example.invalid/" + name,
        content="audited research source " + name,
        rights_refs=("rights:test-fixture",),
    )
    return reg.source(name).content_digest


def _hyp(name: str, prior: float = 0.50) -> Hypothesis:
    return Hypothesis(name, "QUESTION.A", "Proposition " + name,
                      "Falsified by independent contrary measurement.", prior)


def _event(
    source_id: str, digest: str, hypothesis_id: str = "H.A", *,
    event_id: str | None = None, mode: EvidenceMode = EvidenceMode.OBSERVED,
    ratio: float = 3.0, direction: EvidenceDirection = EvidenceDirection.SUPPORTS,
) -> HypothesisEvidence:
    return HypothesisEvidence(
        event_id or "EVENT." + source_id, hypothesis_id,
        source_id, digest, "controlled-source-analysis",
        mode, direction, ratio, ("measurement is context-specific",),
    )


class TestHypothesisEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = ResearchSourceRegistry()
        self.ledger = HypothesisLedger(self.sources)
        self.ledger.register(_hyp("H.A"))
        self.ledger.register(_hyp("H.B"))

    def test_competing_hypotheses_preserved_and_preference_is_provisional(self):
        s1 = _source(self.sources, "SRC.A")
        s2 = _source(self.sources, "SRC.B")
        self.ledger.record(_event("SRC.A", s1))
        self.ledger.record(_event("SRC.B", s2, "H.B", ratio=0.3,
                                  direction=EvidenceDirection.CONTRADICTS))
        result = self.ledger.compare("QUESTION.A")
        self.assertEqual(result.winner, "H.A")
        self.assertEqual(result.resolution, "tentative-preference")
        self.assertEqual(len(result.rankings), 2)
        self.assertEqual(result.rankings[0].classification, "provisional-model-plausibility")
        self.assertGreater(result.rankings[0].plausibility, 0.5)
        self.assertLess(result.rankings[1].plausibility, 0.5)
        self.assertEqual(len(result.receipt_digest), 64)

    def test_simulated_or_interpreted_material_never_updates_observation(self):
        s1 = _source(self.sources, "SRC.A")
        s2 = _source(self.sources, "SRC.B")
        self.ledger.record(_event("SRC.A", s1, mode=EvidenceMode.SIMULATED, ratio=20))
        self.ledger.record(_event("SRC.B", s2, mode=EvidenceMode.INTERPRETED, ratio=20))
        assessment = self.ledger.assess("H.A")
        self.assertEqual(assessment.plausibility, 0.5)
        self.assertEqual(assessment.classification, "unassessed")
        self.assertEqual(assessment.observed_sources, ())
        self.assertEqual(len(assessment.excluded_events), 2)
        self.assertIsNone(self.ledger.compare("QUESTION.A").winner)

    def test_replay_is_idempotent_but_conflicting_identity_is_denied(self):
        digest = _source(self.sources, "SRC.A")
        event = _event("SRC.A", digest)
        first = self.ledger.record(event)
        self.assertEqual(first, self.ledger.record(event))
        with self.assertRaisesRegex(HypothesisError, "identity conflict"):
            self.ledger.record(replace(event, likelihood_ratio=4.0))

    def test_correlated_source_cannot_be_counted_twice(self):
        digest = _source(self.sources, "SRC.A")
        self.ledger.record(_event("SRC.A", digest))
        with self.assertRaisesRegex(HypothesisError, "correlated source"):
            self.ledger.record(_event("SRC.A", digest, event_id="EVENT.AGAIN"))

    def test_same_source_may_be_compared_across_distinct_hypotheses(self):
        digest = _source(self.sources, "SRC.A")
        self.ledger.record(_event("SRC.A", digest))
        self.ledger.record(_event(
            "SRC.A", digest, "H.B", event_id="EVENT.B",
            ratio=0.5, direction=EvidenceDirection.CONTRADICTS,
        ))
        self.assertGreater(self.ledger.assess("H.A").plausibility, 0.5)
        self.assertLess(self.ledger.assess("H.B").plausibility, 0.5)

    def test_retraction_blocks_derived_assessments_until_explicit_withdrawal(self):
        digest = _source(self.sources, "SRC.A")
        event = _event("SRC.A", digest)
        self.ledger.record(event)
        self.sources.transition_source_status(
            "SRC.A", status=SourceStatus.RETRACTED,
            correction_refs=("retraction:001",),
        )
        with self.assertRaisesRegex(HypothesisError, "retracted"):
            self.ledger.assess("H.A")
        with self.assertRaisesRegex(HypothesisError, "retracted"):
            self.ledger.compare("QUESTION.A")
        self.ledger.withdraw(event.event_id, reason="source retracted")
        self.ledger.withdraw(event.event_id, reason="source retracted")
        self.assertEqual(self.ledger.assess("H.A").observed_sources, ())
        self.assertEqual(self.ledger.assess("H.A").classification, "unassessed")
        with self.assertRaisesRegex(HypothesisError, "immutable"):
            self.ledger.withdraw(event.event_id, reason="alternate history")

    def test_retracted_evidence_is_denied_at_ingestion(self):
        digest = _source(self.sources, "SRC.A")
        self.sources.transition_source_status(
            "SRC.A", status=SourceStatus.CORRECTED,
            correction_refs=("correction:1",),
        )
        with self.assertRaisesRegex(HypothesisError, "corrected"):
            self.ledger.record(_event("SRC.A", digest))

    def test_unknown_source_or_digest_mismatch_denied(self):
        with self.assertRaisesRegex(HypothesisError, "unregistered"):
            self.ledger.record(_event("SRC.A", "0" * 64))
        _source(self.sources, "SRC.A")
        with self.assertRaisesRegex(HypothesisError, "digest mismatch"):
            self.ledger.record(_event("SRC.A", "0" * 64))

    def test_strict_direction_ratio_and_probability_validation(self):
        for ratio in (float("nan"), math.inf, -1, 0, 20.1, True):
            with self.subTest(ratio=ratio), self.assertRaises(HypothesisError):
                _event("SRC.A", "a" * 64, ratio=ratio)
        with self.assertRaisesRegex(HypothesisError, "direction"):
            _event("SRC.A", "a" * 64, ratio=0.5)
        with self.assertRaisesRegex(HypothesisError, "direction"):
            _event("SRC.A", "a" * 64, ratio=3,
                   direction=EvidenceDirection.NEUTRAL)
        for prior in (0.0, 1.0, float("nan"), True):
            with self.assertRaises(HypothesisError):
                _hyp("H.A", prior)

    def test_unbound_typeless_or_large_mutations_fail_closed(self):
        with self.assertRaises(HypothesisError):
            HypothesisLedger(self.sources, max_hypotheses=True)
        with self.assertRaises(HypothesisError):
            self.ledger.register(_hyp("H.A", 0.9))
        with self.assertRaises(HypothesisError):
            self.ledger.register(_hyp("H.C" * 200))
        digest = _source(self.sources, "SRC.A")
        with self.assertRaisesRegex(HypothesisError, "not registered"):
            self.ledger.record(_event("SRC.A", digest, "H.UNKNOWN"))
        with self.assertRaisesRegex(HypothesisError, "cannot withdraw"):
            self.ledger.withdraw("EVENT.NO", reason="not found")

    def test_capacity_is_bounded_even_for_valid_events(self):
        ledger = HypothesisLedger(self.sources, max_hypotheses=2, max_evidence=1)
        ledger.register(_hyp("H.A"))
        ledger.register(_hyp("H.B"))
        with self.assertRaisesRegex(HypothesisError, "capacity"):
            ledger.register(_hyp("H.C"))
        first = _source(self.sources, "SRC.A")
        second = _source(self.sources, "SRC.B")
        ledger.record(_event("SRC.A", first))
        with self.assertRaisesRegex(HypothesisError, "capacity"):
            ledger.record(_event("SRC.B", second))

    def test_order_independence_and_receipt_stability(self):
        d1, d2 = _source(self.sources, "SRC.A"), _source(self.sources, "SRC.B")
        a = _event("SRC.A", d1)
        b = _event("SRC.B", d2, ratio=0.5,
                   direction=EvidenceDirection.CONTRADICTS)
        one = HypothesisLedger(self.sources)
        two = HypothesisLedger(self.sources)
        for ledger in (one, two):
            ledger.register(_hyp("H.B"))
            ledger.register(_hyp("H.A"))
        one.record(a); one.record(b)
        two.record(b); two.record(a)
        self.assertEqual(one.assess("H.A"), two.assess("H.A"))
        self.assertEqual(one.compare("QUESTION.A"), two.compare("QUESTION.A"))

    def test_comparison_requires_more_than_one_hypothesis(self):
        ledger = HypothesisLedger(self.sources)
        ledger.register(_hyp("H.A"))
        with self.assertRaisesRegex(HypothesisError, "at least two"):
            ledger.compare("QUESTION.A")

    def test_score_cannot_overflow_and_does_not_promote_truth(self):
        for n in range(55):
            src = "SRC." + str(n)
            digest = _source(self.sources, src)
            self.ledger.record(_event(src, digest))
        value = self.ledger.assess("H.A")
        self.assertTrue(math.isfinite(value.plausibility))
        self.assertLess(value.plausibility, 1.0)
        self.assertEqual(value.classification, "provisional-model-plausibility")


    def test_unbounded_integer_prior_is_denied_by_contract(self):
        with self.assertRaises(HypothesisError):
            _hyp("H.OVERFLOW", prior=10 ** 1000)

if __name__ == "__main__":
    unittest.main()
