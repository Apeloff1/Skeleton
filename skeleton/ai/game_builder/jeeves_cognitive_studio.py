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
