from __future__ import annotations

import unittest

from skeleton.jeeves.domain_system import (
    DomainDefinition,
    DomainEvidence,
    DomainExecutionContext,
    DomainIntelligenceError,
    DomainRegistry,
    EvidenceClass,
    LearnerState,
    TeachingPolicy,
)
from skeleton.simulation.environment import DeterministicEnvironmentAdapter


class P3DomainIntelligenceTests(unittest.TestCase):
    def _registry(self, *, simulation_allowed: bool = False) -> DomainRegistry:
        registry = DomainRegistry()
        registry.register(
            DomainDefinition(
                domain_id="jeeves.markets",
                custody_id="custody:jeeves",
                purpose="domain-analysis",
                allowed_capabilities=("analyze", "simulate"),
                evaluation_owner="eval:markets-independent",
                max_evidence_age_seconds=60.0,
                simulation_allowed=simulation_allowed,
            )
        )
        return registry

    def _evidence(self) -> DomainEvidence:
        return DomainEvidence.from_payload(
            evidence_id="ev-1",
            evidence_class=EvidenceClass.OBSERVATION,
            observed_at=100.0,
            source_refs=("source:market-feed",),
            provenance_refs=("prov:feed:1",),
            payload={"value": 10},
            uncertainty=0.1,
        )

    def test_registered_domain_authorizes_only_custodied_capability(self) -> None:
        decision = self._registry().authorize(
            DomainExecutionContext(
                domain_id="jeeves.markets",
                custody_id="custody:jeeves",
                capability="analyze",
                evidence=(self._evidence(),),
                requested_at=120.0,
                purpose="domain-analysis",
            )
        )
        self.assertEqual(decision.evaluation_owner, "eval:markets-independent")
        self.assertTrue(decision.real_world_fact_authority)

    def test_parallel_custody_is_rejected(self) -> None:
        with self.assertRaisesRegex(DomainIntelligenceError, "custody mismatch"):
            self._registry().authorize(
                DomainExecutionContext(
                    domain_id="jeeves.markets",
                    custody_id="parallel-jeeves",
                    capability="analyze",
                    evidence=(self._evidence(),),
                    requested_at=120.0,
                    purpose="domain-analysis",
                )
            )

    def test_out_of_domain_capability_fails_closed(self) -> None:
        with self.assertRaisesRegex(DomainIntelligenceError, "out-of-domain"):
            self._registry().authorize(
                DomainExecutionContext(
                    domain_id="jeeves.markets",
                    custody_id="custody:jeeves",
                    capability="execute-trade",
                    evidence=(self._evidence(),),
                    requested_at=120.0,
                    purpose="domain-analysis",
                )
            )

    def test_stale_evidence_is_rejected(self) -> None:
        with self.assertRaisesRegex(DomainIntelligenceError, "stale"):
            self._registry().authorize(
                DomainExecutionContext(
                    domain_id="jeeves.markets",
                    custody_id="custody:jeeves",
                    capability="analyze",
                    evidence=(self._evidence(),),
                    requested_at=200.0,
                    purpose="domain-analysis",
                )
            )

    def test_simulation_is_never_real_world_fact_authority(self) -> None:
        def reducer(state, action, seed):
            return {"x": int(state["x"]) + int(action["dx"])}, 1.0, False, 0.25

        env = DeterministicEnvironmentAdapter(
            simulation_id="world-fixture",
            initial_state={"x": 0},
            reducer=reducer,
        )
        transition = env.step({"dx": 1})
        evidence = DomainEvidence.from_simulation(
            "sim-ev",
            transition.evidence,
            observed_at=100.0,
            provenance_refs=("prov:sim:1",),
        )
        decision = self._registry(simulation_allowed=True).authorize(
            DomainExecutionContext(
                domain_id="jeeves.markets",
                custody_id="custody:jeeves",
                capability="simulate",
                evidence=(evidence,),
                requested_at=101.0,
                purpose="domain-analysis",
            )
        )
        self.assertFalse(decision.real_world_fact_authority)
        self.assertEqual(decision.uncertainty, 0.25)

    def test_simulation_requires_explicit_domain_permission(self) -> None:
        def reducer(state, action, seed):
            return {"x": 1}, 0.0, True, 0.3

        evidence = DomainEvidence.from_simulation(
            "sim-ev",
            DeterministicEnvironmentAdapter(
                simulation_id="sim",
                initial_state={"x": 0},
                reducer=reducer,
            ).step({"dx": 1}).evidence,
            observed_at=1.0,
            provenance_refs=("prov:sim",),
        )
        with self.assertRaisesRegex(DomainIntelligenceError, "not allowed"):
            self._registry().authorize(
                DomainExecutionContext(
                    domain_id="jeeves.markets",
                    custody_id="custody:jeeves",
                    capability="simulate",
                    evidence=(evidence,),
                    requested_at=2.0,
                    purpose="domain-analysis",
                )
            )

    def test_teaching_policy_exposes_uncertainty_and_eval_owner(self) -> None:
        state = LearnerState(
            learner_id="learner-1",
            skill_id="fractions",
            mastery=0.7,
            uncertainty=0.2,
            evidence_ids=("assessment:1",),
            observed_at=100.0,
        )
        rec = TeachingPolicy(evaluation_owner="eval:pedagogy").recommend(state)
        self.assertEqual(rec.action, "practice")
        self.assertEqual(rec.evaluation_owner, "eval:pedagogy")
        self.assertEqual(rec.evidence_ids, ("assessment:1",))

    def test_teaching_policy_requests_more_evidence_when_uncertain(self) -> None:
        state = LearnerState(
            learner_id="learner-1",
            skill_id="fractions",
            mastery=0.9,
            uncertainty=0.8,
            evidence_ids=("assessment:noisy",),
            observed_at=100.0,
        )
        rec = TeachingPolicy(evaluation_owner="eval:pedagogy").recommend(state)
        self.assertEqual(rec.action, "gather_more_evidence")
        self.assertEqual(rec.target_difficulty, 0.9)


if __name__ == "__main__":
    unittest.main()
