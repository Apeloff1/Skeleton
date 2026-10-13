"""Run existing canonical uncertainty, cognitive strategy and stopping gates.

No model inference, self-authorized verification or source writes. High-risk
verification is never derived from caller-supplied candidate state.
"""
from __future__ import annotations

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest

SCHEMA = "skeleton.ai.jeeves_cognitive_studio.v1"
POLICY = {
    "policy_id": "jeeves_studio_cognition",
    "version": 1,
    "allowed_strategies": ["direct","retrieve","decompose","search",
                           "verify","reflect","critique","repair"],
    "default_strategy": "direct",
    "max_steps": 24,
    "max_tokens": 16000,
    "max_cost_units": 100.0,
    "max_wall_time_s": 90.0,
    "min_value_of_information": 0.15,
    "completion_confidence": 0.88,
    "max_uncertainty": 0.35,
    "max_stall_steps": 4,
    "require_verification_for_high_risk": True,
}
CANDIDATE_KEYS = frozenset((
    "strategy","expected_quality","expected_uncertainty_reduction",
    "expected_cost_units","expected_tokens","expected_wall_time_s",
    "verification_capable",
))
STEP_KEYS = frozenset((
    "step_index","cumulative_tokens","cumulative_cost_units","elapsed_s",
    "confidence","uncertainty","value_of_information","progress_digest",
    "verification_passed","explicit_stop",
))


def _bounded_payload(value, maximum=75000):
    from .jeeves_appwide_fabric import canonical
    if len(canonical(value).encode("utf-8")) > maximum:
        raise JeevesAppwideError("bounded cognitive input payload exceeded")


def _policy(values):
    from skeleton.intelligence.strategy_registry import ReasoningPolicy
    if values is None:
        data = dict(POLICY)
    elif type(values) is dict and not set(values)-set(POLICY):
        data = {**POLICY, **values}
    else:
        raise JeevesAppwideError("unknown reasoning policy field")
    _bounded_payload(data, 8000)
    if (type(data["allowed_strategies"]) is not list or
            not 1 <= len(data["allowed_strategies"]) <= 8):
        raise JeevesAppwideError("bounded typed reasoning strategy list required")
    data["allowed_strategies"] = tuple(data["allowed_strategies"])
    return ReasoningPolicy(**data)


def _risk(value):
    from skeleton.intelligence.strategy_registry import ReasoningRisk
    try:
        return ReasoningRisk(value)
    except ValueError as exc:
        raise JeevesAppwideError("known risk category required") from exc


class JeevesCognitiveStudio:
    """Real installed bounded cognitive gates exposed through reviewed Jeeves."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical application inventory required")
        inventory._require_scanned()
        self.inv = inventory

    def _snapshot(self, expected_snapshot):
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("stale cognitive source snapshot")

    def uncertainty(self, *, candidates, answer_threshold=0.65,
                    escalate_threshold=0.40, min_agreement=0.5,
                    expected_snapshot=None):
        from skeleton.intelligence.uncertainty import (
            Candidate, UncertaintyGate, explain_decision,
        )
        self._snapshot(expected_snapshot)
        if type(candidates) is not list or len(candidates)>16 or any(
            type(c) is not dict or set(c)!={"text","confidence"}
            or type(c["text"]) is not str
            or not 1<=len(c["text"].encode("utf-8"))<=2500
            for c in candidates
        ):
            raise JeevesAppwideError("0–16 bounded text/confidence candidates required")
        _bounded_payload(candidates)
        decision=UncertaintyGate(
            answer_threshold=answer_threshold,
            escalate_threshold=escalate_threshold,
            min_agreement=min_agreement,
        ).decide([Candidate(**row) for row in candidates])
        body={
            "schema":SCHEMA+".uncertainty",
            "inventory_snapshot":self.inv._digest,
            "decision":decision.to_dict(),
            "explanation":explain_decision(decision).to_dict(),
            "candidate_digest":digest(candidates),
            "actual_installed_uncertainty_gate_executed":True,
            "self_confidence_not_calibrated_probability":True,
            "model_inference_or_weights_changed":False,
        }
        return {**body,"digest":digest(body)}

    def strategy(self, *, candidates, risk="medium", policy=None,
                 expected_snapshot=None):
        from skeleton.intelligence.strategy_registry import (
            StrategyCandidate, select_strategy,
        )
        self._snapshot(expected_snapshot)
        if (type(candidates) is not list or not 1<=len(candidates)<=16
                or any(type(row) is not dict or set(row)!=CANDIDATE_KEYS
                       for row in candidates)):
            raise JeevesAppwideError("1–16 exact strategy candidate definitions required")
        _bounded_payload(candidates)
        selected_policy=_policy(policy)
        decision=select_strategy(
            selected_policy,[StrategyCandidate(**row) for row in candidates],
            risk=_risk(risk))
        body={
            "schema":SCHEMA+".strategy",
            "inventory_snapshot":self.inv._digest,
            "policy_digest":selected_policy.digest,
            "selection":decision.payload(),
            "selection_digest":decision.digest,
            "candidate_digest":digest(candidates),
            "actual_bounded_reasoning_strategy_selected":True,
            "high_risk_verification_capability_required":True,
            "model_inference_or_qualification_performed":False,
        }
        return {**body,"digest":digest(body)}

    def build_plan(self, *, plan, vision, expected_snapshot=None):
        """Run the installed original-game plan quality gate, not a new scorer.

        This is a deterministic heuristic receipt from canonical PlanVerifier,
        not an independent implementation or consumer playability acceptance.
        """
        from skeleton.intelligence.plan_verifier import PlanVerifier
        self._snapshot(expected_snapshot)
        if (type(plan) is not dict or not 1 <= len(plan) <= 16 or
                type(vision) is not str or not 12 <= len(vision) <= 4000):
            raise JeevesAppwideError("bounded original game build vision and plan required")
        allowed = frozenset((
            "era", "primary_dps", "room_bias", "title", "citation", "url",
        ))
        if set(plan) - allowed or any(
                type(value) is not str or not 1 <= len(value) <= 1000
                for value in plan.values()):
            raise JeevesAppwideError("reviewed bounded game plan fields required")
        _bounded_payload({"plan":plan, "vision":vision}, 16000)
        receipt=PlanVerifier().verify(plan, vision=vision)
        body={
            "schema":SCHEMA+".build_plan",
            "inventory_snapshot":self.inv._digest,
            "source_plan_digest":digest(plan),
            "source_vision_digest":digest(vision),
            "canonical_installed_game_plan_verifier_executed":True,
            "plan_quality_heuristic":receipt.to_dict(),
            "quality_result_is_not_independent_runtime_qualification":True,
            "game_code_compiled_or_executed":False,
            "model_weights_and_sources_changed":False,
        }
        return {**body, "digest":digest(body)}

    def static_plan(self, *, plan_id, steps, initial_facts,
                    risk="medium", inject_failure_at=None,
                    expected_snapshot=None):
        """Execute installed DAG analyzer and bounded fault-injection simulator.

        This is source-level *simulation*, not real executor dispatch. It
        cannot grant privileged capabilities, launch jobs or mutate source.
        """
        from skeleton.intelligence.plan_verifier import (
            PlanStep, StaticPlanDefinition, PlanVerificationPolicy,
            analyze_static_plan, simulate_static_plan,
        )
        self._snapshot(expected_snapshot)
        if (type(plan_id) is not str or not 1 <= len(plan_id) <= 96
                or type(steps) is not list or not 1 <= len(steps) <= 96
                or type(initial_facts) is not list
                or len(initial_facts) > 128):
            raise JeevesAppwideError("bounded original static plan required")
        known = frozenset((
            "source.read", "source.inspect", "game.preview",
            "forge.preview", "cognition.evaluate", "plan.inspect",
        ))
        allowed = frozenset((
            "step_id", "depends_on", "preconditions", "postconditions",
            "required_capabilities", "max_tokens", "max_cost_units",
            "max_wall_time_s", "terminal", "side_effect",
            "irreversible", "recovery_plan_digest", "rollback_test_digest",
        ))
        if any(
            type(row) is not dict or set(row) - allowed
            or "step_id" not in row
            or type(row.get("required_capabilities", [])) not in (tuple,list)
            or not all(
                type(cap) is str and cap in known
                for cap in row.get("required_capabilities", [])
            )
            or any(
                key in row and (
                    type(row[key]) not in (tuple,list)
                    or len(row[key]) > 128
                    or not all(type(item) is str for item in row[key])
                )
                for key in (
                    "depends_on", "preconditions", "postconditions"
                )
            )
            for row in steps
        ):
            raise JeevesAppwideError("unknown or privileged source plan capability")
        _bounded_payload({
            "plan_id":plan_id, "steps":steps, "initial_facts":initial_facts
        }, 150000)
        canon_policy = _policy(None)
        plan=StaticPlanDefinition(
            plan_id=plan_id, version=1,
            steps=tuple(PlanStep(**{
                **row,
                **{
                    k:tuple(row[k]) for k in (
                        "depends_on", "preconditions",
                        "postconditions", "required_capabilities"
                    ) if k in row
                },
            }) for row in steps),
            initial_facts=tuple(initial_facts),
            reasoning_policy_digest=canon_policy.digest,
            planning_history_digest=digest(steps),
            risk=_risk(risk),
        )
        policy=PlanVerificationPolicy(
            policy_id="jeeves_readonly_static_plan",
            version=1,
            allowed_capabilities=tuple(sorted(known)),
            max_steps=96,
            max_total_tokens=80000,
            max_total_cost_units=200.0,
            max_total_wall_time_s=300.0,
            require_terminal_leaves=True,
            allow_irreversible=False,
        )
        analysis=analyze_static_plan(plan,policy)
        simulation=simulate_static_plan(
            plan,analysis,
            available_capabilities=tuple(sorted(known)),
            injected_failure_step_id=inject_failure_at,
        )
        body={
            "schema":SCHEMA+".static_plan",
            "inventory_snapshot":self.inv._digest,
            "canonical_plan_digest":plan.digest,
            "canonical_policy_digest":policy.digest,
            "static_analysis":analysis.payload(),
            "static_analysis_digest":analysis.decision_digest,
            "fault_injection_simulation":simulation.payload(),
            "fault_injection_receipt_digest":simulation.decision_digest,
            "actual_canonical_dag_analyzer_executed":True,
            "actual_canonical_fault_simulator_executed":True,
            "source_execution_or_job_dispatch_performed":False,
            "privileged_capabilities_allowed":False,
            "real_side_effects_or_jobs_executed":False,
            "simulated_reversible_side_effect_steps_may_be_present":True,
            "plan_is_not_independently_product_qualified":True,
        }
        return {**body,"digest":digest(body)}

    def stopping(self, *, history, risk="medium", policy=None,
                 expected_snapshot=None):
        from skeleton.intelligence.strategy_registry import (
            ReasoningStep, evaluate_stopping,
        )
        self._snapshot(expected_snapshot)
        if (type(history) is not list or not 1<=len(history)<=64
                or any(type(row) is not dict or set(row)!=STEP_KEYS
                       for row in history)):
            raise JeevesAppwideError("1–64 complete bounded reasoning steps required")
        _bounded_payload(history)
        selected_policy=_policy(policy)
        # A caller boolean is not an independent verified result. Never
        # allow it to satisfy the canonical high-risk completion gate.
        safe_history=[
            {**row,"verification_passed":False} for row in history
        ]
        decision=evaluate_stopping(
            selected_policy,[ReasoningStep(**row) for row in safe_history],
            risk=_risk(risk))
        body={
            "schema":SCHEMA+".stopping",
            "inventory_snapshot":self.inv._digest,
            "policy_digest":selected_policy.digest,
            "decision":decision.payload(),
            "decision_digest":decision.decision_digest,
            "step_count":len(history),
            "actual_canonical_stopping_policy_executed":True,
            "caller_claimed_verification_ignored":True,
            "independent_verification_not_observed":True,
            "model_weights_and_project_sources_unchanged":True,
        }
        return {**body,"digest":digest(body)}
