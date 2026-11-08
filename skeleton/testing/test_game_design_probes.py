"""VOL-249..252 integration: provenance, game-design preview and bounded control."""
from __future__ import annotations

from dataclasses import replace
import math
import unittest

from skeleton.ai.research.causal_knowledge import (
    CausalClaim, CausalGraph, CausalKnowledgeError, ClaimKind,
)
from skeleton.ai.research.game_design_probes import (
    DesignProbePlanner, DesignProbeRequest, ProbeEvidenceStatus,
    ProbePlanningError,
)
from skeleton.ai.research.hypothesis_engine import (
    EvidenceDirection, EvidenceMode, Hypothesis, HypothesisError,
    HypothesisEvidence, HypothesisLedger,
)
from skeleton.ai.research.source_lineage import ResearchSourceRegistry, SourceStatus
from skeleton.intelligence.strategy_registry import (
    ReasoningPolicy, ReasoningRisk, ReasoningStep, ReasoningStrategy,
    StopDisposition, StrategyCandidate,
)


def _source(reg: ResearchSourceRegistry, key: str) -> str:
    reg.ingest(
        source_id=key,
        uri="https://example.invalid/" + key,
        content="Synthetic, consented playtest signal: " + key,
        rights_refs=("rights:test-fixture",),
    )
    return reg.source(key).content_digest


def _policy(*, steps: int = 5, max_tokens: int = 500,
            min_value: float = 0.10) -> ReasoningPolicy:
    return ReasoningPolicy(
        policy_id="POLICY.GAME.PROBES", version=1,
        allowed_strategies=(
            ReasoningStrategy.SEARCH, ReasoningStrategy.VERIFY,
            ReasoningStrategy.DIRECT,
        ),
        default_strategy=ReasoningStrategy.SEARCH,
        max_steps=steps, max_tokens=max_tokens, max_cost_units=5,
        max_wall_time_s=120, min_value_of_information=min_value,
        completion_confidence=0.9, max_uncertainty=0.8, max_stall_steps=2,
    )


def _history(*, index: int = 1, tokens: int = 100, uncertainty: float = 0.6,
             value: float = 0.7, confidence: float = 0.3,
             verified: bool = False, stop: bool = False) -> ReasoningStep:
    return ReasoningStep(
        step_index=index, cumulative_tokens=tokens,
        cumulative_cost_units=0.5, elapsed_s=2.0,
        confidence=confidence, uncertainty=uncertainty,
        value_of_information=value, progress_digest="a" * 64,
        verification_passed=verified, explicit_stop=stop,
    )


def _candidates(*, verification: bool = True) -> tuple[StrategyCandidate, ...]:
    return (
        StrategyCandidate(
            ReasoningStrategy.SEARCH, 0.8, 0.7, 0.5, 150, 5.0,
            verification_capable=False,
        ),
        StrategyCandidate(
            ReasoningStrategy.VERIFY, 0.75, 0.5, 0.7, 200, 8.0,
            verification_capable=verification,
        ),
        StrategyCandidate(
            ReasoningStrategy.DIRECT, 0.2, 0.1, 0, 20, 1,
            verification_capable=False,
        ),
    )


def _request(*, risk: ReasoningRisk = ReasoningRisk.HIGH, model: bool = False,
             preview: bool = False) -> DesignProbeRequest:
    return DesignProbeRequest(
        "PROBE.QUEST.PACING", "GAME.ORIGINAL", "QUESTION.PACING",
        "Measured quest completion rate by difficulty tier", risk,
        "Pacing" if preview else None,
        2.0 if preview else None,
        model,
    )


class TestGameDesignProbes(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = ResearchSourceRegistry()
        self.ledger = HypothesisLedger(self.sources)
        self.graph = CausalGraph(self.sources)
        self.planner = DesignProbePlanner(self.sources, self.ledger, self.graph)
        self.ledger.register(Hypothesis(
            "H.PACING", "QUESTION.PACING",
            "Shorter objectives increase quest completion",
            "Independent samples find no improvement", 0.5,
        ))
        self.ledger.register(Hypothesis(
            "H.DIFFICULTY", "QUESTION.PACING",
            "Difficulty alone explains completion differences",
            "Controlled strata show no difficulty difference", 0.5,
        ))

    def add_evidence(self) -> str:
        digest = _source(self.sources, "SRC.PLAYTEST")
        self.ledger.record(HypothesisEvidence(
            "EVENT.PLAYTEST", "H.PACING", "SRC.PLAYTEST", digest,
            "observational playtest stratification",
            EvidenceMode.OBSERVED, EvidenceDirection.SUPPORTS, 3,
            ("sample limited to offline sandbox sessions",),
        ))
        return digest

    def add_model(self, *, kind: ClaimKind = ClaimKind.IDENTIFIED_MODEL,
                  confounders: tuple[str, ...] = ()) -> None:
        digest = _source(self.sources, "SRC.MODEL")
        self.graph.add(CausalClaim(
            "EDGE.PACING.RETENTION", "Pacing", "Retention",
            "SRC.MODEL", digest, "explicit structural model",
            kind, ("linearized sandbox response",), confounders,
            None if kind is ClaimKind.ASSOCIATION else 0.5,
        ))

    def plan(self, **kwargs):
        return self.planner.plan(
            _request(**kwargs), _policy(), _candidates(), (_history(),),
        )

    def test_cross_plane_plan_has_digest_and_no_action_authority(self):
        self.add_evidence()
        self.add_model()
        plan = self.plan(preview=True)
        self.assertEqual(plan.evidence_status, ProbeEvidenceStatus.TENTATIVE)
        self.assertEqual(plan.comparison.winner, "H.PACING")
        self.assertTrue(plan.source_ids == ("SRC.MODEL", "SRC.PLAYTEST"))
        self.assertEqual(plan.control.stopping.disposition, StopDisposition.CONTINUE)
        self.assertEqual(plan.next_strategy, ReasoningStrategy.VERIFY.value)
        self.assertEqual(dict(plan.simulation.simulated_deltas), {
            "Pacing": 2.0, "Retention": 1.0,
        })
        self.assertFalse(plan.executable)
        self.assertFalse(plan.simulation.observed)
        self.assertEqual(plan.payload()["execution_authorized"], False)
        self.assertEqual(plan.payload()["observation_verified"], False)
        self.assertEqual(plan.payload()["simulation_kind"], "SIMULATION_NOT_OBSERVATION")
        self.assertEqual(len(plan.receipt_digest), 64)

    def test_identical_inputs_replay_same_receipt(self):
        self.add_evidence()
        self.add_model()
        first = self.plan(preview=True)
        second = self.plan(preview=True)
        self.assertEqual(first, second)
        self.assertEqual(first.payload(), second.payload())

    def test_empty_observations_never_claim_success(self):
        result = self.plan()
        self.assertEqual(result.evidence_status, ProbeEvidenceStatus.UNASSESSED)
        self.assertIsNone(result.comparison.winner)
        self.assertFalse(result.executable)
        self.assertIsNone(result.simulation)

    def test_nonobservational_events_are_not_treated_as_measurements(self):
        digest = _source(self.sources, "SRC.SIM")
        self.ledger.record(HypothesisEvidence(
            "EVENT.SIM", "H.PACING", "SRC.SIM", digest,
            "sandbox result", EvidenceMode.SIMULATED,
            EvidenceDirection.SUPPORTS, 20, ("not a measurement",),
        ))
        result = self.plan()
        self.assertEqual(result.evidence_status, ProbeEvidenceStatus.UNASSESSED)
        self.assertNotIn("SRC.SIM", result.source_ids)

    def test_tied_observed_hypotheses_remain_contested(self):
        d1 = self.add_evidence()
        d2 = _source(self.sources, "SRC.OTHER")
        self.ledger.record(HypothesisEvidence(
            "EVENT.OTHER", "H.DIFFICULTY", "SRC.OTHER", d2,
            "matched source", EvidenceMode.OBSERVED,
            EvidenceDirection.SUPPORTS, 3, ("synthetic game test",),
        ))
        plan = self.plan()
        self.assertEqual(plan.evidence_status, ProbeEvidenceStatus.CONTESTED)
        self.assertIsNone(plan.comparison.winner)

    def test_retracted_hypothesis_source_invalidates_plan(self):
        self.add_evidence()
        self.sources.transition_source_status(
            "SRC.PLAYTEST", status=SourceStatus.RETRACTED,
            correction_refs=("retracted:fixture",),
        )
        with self.assertRaises(HypothesisError):
            self.plan()

    def test_retracted_model_source_invalidates_plan(self):
        self.add_model()
        self.sources.transition_source_status(
            "SRC.MODEL", status=SourceStatus.CORRECTED,
            correction_refs=("corrected:fixture",),
        )
        with self.assertRaises(CausalKnowledgeError):
            self.plan()

    def test_independent_registries_cannot_be_joined(self):
        other = ResearchSourceRegistry()
        with self.assertRaisesRegex(ProbePlanningError, "same"):
            DesignProbePlanner(other, self.ledger, self.graph)
        with self.assertRaisesRegex(ProbePlanningError, "same"):
            DesignProbePlanner(self.sources, HypothesisLedger(other), self.graph)
        with self.assertRaisesRegex(ProbePlanningError, "same"):
            DesignProbePlanner(self.sources, self.ledger, CausalGraph(other))

    def test_association_model_never_influences_intervention(self):
        self.add_model(kind=ClaimKind.ASSOCIATION)
        plan = self.plan(preview=True)
        self.assertEqual(plan.simulation.simulated_deltas, (("Pacing", 2.0),))
        self.assertEqual(plan.simulation.model_claim_ids, ())
        self.assertFalse(plan.executable)

    def test_confounding_refuses_preview_even_if_explicitly_hypothetical(self):
        self.add_model(
            kind=ClaimKind.CAUSAL_HYPOTHESIS, confounders=("selection-bias",),
        )
        with self.assertRaisesRegex(CausalKnowledgeError, "confounders"):
            self.plan(preview=True, model=True)

    def test_hypothesized_model_requires_specific_opt_in(self):
        self.add_model(kind=ClaimKind.CAUSAL_HYPOTHESIS)
        with self.assertRaisesRegex(CausalKnowledgeError, "opt-in"):
            self.plan(preview=True)
        result = self.plan(preview=True, model=True)
        self.assertFalse(result.simulation.observed)
        self.assertFalse(result.executable)

    def test_critical_risk_never_reserves_unverified_search_candidate(self):
        candidates = _candidates()
        plan = self.planner.plan(
            _request(risk=ReasoningRisk.CRITICAL), _policy(), candidates,
            (_history(),),
        )
        self.assertEqual(plan.next_strategy, ReasoningStrategy.VERIFY.value)
        self.assertTrue(plan.control.reservation is not None)
        self.assertFalse(plan.executable)

    def test_high_risk_without_verifying_strategy_fails_closed(self):
        plan = self.planner.plan(
            _request(), _policy(), _candidates(verification=False),
            (_history(),),
        )
        self.assertIsNone(plan.next_strategy)
        self.assertEqual(
            plan.control.stopping.disposition,
            StopDisposition.BUDGET_EXHAUSTED,
        )
        self.assertFalse(plan.executable)

    def test_budget_exhaustion_stops_without_next_strategy(self):
        result = self.planner.plan(
            _request(), _policy(max_tokens=100), _candidates(),
            (_history(tokens=100),),
        )
        self.assertEqual(
            result.control.stopping.disposition,
            StopDisposition.BUDGET_EXHAUSTED,
        )
        self.assertIsNone(result.next_strategy)

    def test_explicit_stop_never_reserves_provider_step(self):
        result = self.planner.plan(
            _request(), _policy(), _candidates(),
            (_history(stop=True),),
        )
        self.assertEqual(result.control.stopping.disposition, StopDisposition.ABSTAIN)
        self.assertIsNone(result.next_strategy)

    def test_high_confidence_is_not_mistaken_for_verified_observation(self):
        result = self.planner.plan(
            _request(), _policy(), _candidates(),
            (_history(confidence=0.99, verified=True),),
        )
        self.assertEqual(result.control.stopping.disposition, StopDisposition.COMPLETE)
        self.assertFalse(result.executable)
        self.assertFalse(result.payload()["observation_verified"])

    def test_uncertainty_policy_escalation_is_preserved(self):
        result = self.planner.plan(
            _request(), _policy(), _candidates(),
            (_history(uncertainty=0.9),),
        )
        self.assertEqual(result.control.stopping.disposition, StopDisposition.ESCALATE)
        self.assertIsNone(result.next_strategy)

    def test_low_value_of_information_never_purchases_next_step(self):
        result = self.planner.plan(
            _request(), _policy(min_value=0.5), _candidates(),
            (_history(value=0.1),),
        )
        self.assertEqual(result.control.stopping.disposition, StopDisposition.VALUE_EXHAUSTED)
        self.assertIsNone(result.next_strategy)

    def test_candidate_order_has_no_effect_on_admission_receipt(self):
        self.add_evidence()
        candidates = _candidates()
        first = self.planner.plan(
            _request(), _policy(), candidates, (_history(),),
        )
        second = self.planner.plan(
            _request(), _policy(), tuple(reversed(candidates)), (_history(),),
        )
        self.assertEqual(first.receipt_digest, second.receipt_digest)
        self.assertEqual(first.next_strategy, second.next_strategy)

    def test_invalid_request_shapes_are_rejected_at_boundary(self):
        for changes in (
            {"probe_id": "bad token"},
            {"project_id": ""},
            {"metric": " incorrect whitespace "},
            {"risk": "high"},
            {"intervention_delta": 1.0},
            {"intervention_variable": "Pacing"},
            {"allow_hypothesized_model": True},
            {"intervention_variable": "Pacing", "intervention_delta": True},
            {"intervention_variable": "Pacing", "intervention_delta": math.inf},
            {"intervention_variable": "Pacing", "intervention_delta": 12},
        ):
            with self.subTest(changes=changes), self.assertRaises(ProbePlanningError):
                replace(_request(), **changes)

    def test_unbounded_candidates_and_history_are_stopped_before_owner(self):
        def many_candidates():
            while True:
                yield _candidates()[0]
        def many_history():
            while True:
                yield _history()
        with self.assertRaisesRegex(ProbePlanningError, "candidate"):
            self.planner.plan(
                _request(), _policy(), many_candidates(), (_history(),),
            )
        with self.assertRaisesRegex(ProbePlanningError, "history"):
            self.planner.plan(
                _request(), _policy(), _candidates(), many_history(),
            )

    def test_receipt_changes_when_metric_risk_or_model_changes(self):
        self.add_evidence()
        self.add_model()
        baseline = self.plan()
        revised = self.planner.plan(
            replace(_request(), metric="Changed measurable metric"),
            _policy(), _candidates(), (_history(),),
        )
        simulated = self.plan(preview=True)
        self.assertNotEqual(baseline.receipt_digest, revised.receipt_digest)
        self.assertNotEqual(baseline.receipt_digest, simulated.receipt_digest)

    def test_history_and_decision_identity_enter_receipt(self):
        first = self.plan()
        second = self.planner.plan(
            _request(), _policy(), _candidates(), (_history(),),
            decision_index=2,
            previous_decision_digest=first.control.decision_digest,
        )
        self.assertNotEqual(first.receipt_digest, second.receipt_digest)
        self.assertEqual(second.control.previous_decision_digest,
                         first.control.decision_digest)


    def test_unbounded_integer_intervention_is_denied_by_contract(self):
        with self.assertRaises(ProbePlanningError):
            replace(_request(preview=True), intervention_delta=10 ** 1000)

if __name__ == "__main__":
    unittest.main()
