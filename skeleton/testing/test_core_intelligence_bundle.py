from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.intelligence.core_intelligence import (
    CoreIntelligenceError,
    qualify_core_intelligence,
)
from skeleton.intelligence.memory_retrieval_quality import (
    IntelligenceQualityDecision,
)
from skeleton.intelligence.output_quality import AnswerArtifactQualityDecision
from skeleton.intelligence.plan_verifier import PlanQualificationDecision
from skeleton.intelligence.routing_context_receipt import RoutingContextReceipt
from skeleton.intelligence.strategy_registry import (
    StopDisposition,
    StoppingDecision,
)


def _routing(**overrides: object) -> RoutingContextReceipt:
    values: dict[str, object] = {
        "operation_id": "operation-1",
        "execution_id": "execution-1",
        "turn_id": "turn-1",
        "tenant_id": "tenant-1",
        "request_id": "request-1",
        "context_id": "context-1",
        "context_digest": "a" * 64,
        "request_digest": "b" * 64,
        "route_plan_digest": "c" * 64,
        "route_result_digest": "d" * 64,
        "admission_decision_id": "admission-1",
        "admission_status": "admit",
        "admission_reason": "within-bounds",
        "route_status": "ok",
        "selected_provider_id": "provider-1",
        "planned_provider_ids": ("provider-1",),
        "fallback_provider_ids": (),
        "required_capabilities": ("text",),
        "context_tokens": 100,
        "context_capacity": 1000,
        "trust_counts": (("trusted", 1),),
        "data_class_counts": (("internal", 1),),
        "omission_reason_counts": (),
        "max_selected_data_class": "internal",
        "max_allowed_data_class": "confidential",
        "quality_score": 0.95,
        "quality_floor": 0.80,
        "quality_accepted": True,
        "quality_digest": "e" * 64,
        "spent_cost": 0.10,
        "remaining_cost": 0.90,
        "spent_output_tokens": 50,
        "remaining_output_tokens": 950,
        "deadline_seconds": 30.0,
        "observed_attempt_latency_seconds": 0.25,
        "blockers": (),
        "eligible_for_promotion": True,
    }
    values.update(overrides)
    return RoutingContextReceipt(**values)


def _intelligence(**overrides: object) -> IntelligenceQualityDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "memory_digest": "1" * 64,
        "conflict_digest": "2" * 64,
        "retrieval_digest": "3" * 64,
        "retrieval_provenance_digest": "4" * 64,
        "freshness_digest": "5" * 64,
        "knowledge_digest": "6" * 64,
        "quality_digest": "e" * 64,
        "policy_digest": "7" * 64,
        "observed_at": 1_800_000_000.0,
    }
    values.update(overrides)
    return IntelligenceQualityDecision(**values)


def _stopping(**overrides: object) -> StoppingDecision:
    values: dict[str, object] = {
        "disposition": StopDisposition.COMPLETE,
        "reason": "quality-complete",
        "policy_digest": "8" * 64,
        "history_digest": "9" * 64,
        "steps_remaining": 2,
        "tokens_remaining": 1000,
        "cost_remaining": 2.0,
        "time_remaining_s": 20.0,
    }
    values.update(overrides)
    return StoppingDecision(**values)


def _output(**overrides: object) -> AnswerArtifactQualityDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "answer_evaluation_digest": "a" * 64,
        "artifact_evaluation_digests": ("b" * 64,),
        "regression_digests": ("c" * 64,),
        "policy_digest": "d" * 64,
    }
    values.update(overrides)
    return AnswerArtifactQualityDecision(**values)


def _plan(
    stopping: StoppingDecision,
    **overrides: object,
) -> PlanQualificationDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "plan_digest": "e" * 64,
        "verification_policy_digest": "f" * 64,
        "reasoning_policy_digest": stopping.policy_digest,
        "analysis_digest": "1" * 64,
        "simulation_digest": "2" * 64,
        "stopping_digest": stopping.decision_digest,
        "risk_evaluation_digest": "3" * 64,
    }
    values.update(overrides)
    return PlanQualificationDecision(**values)


def _chain():
    stopping = _stopping()
    return (
        _routing(),
        _intelligence(),
        stopping,
        _output(),
        _plan(stopping),
    )


def test_accepts_exact_core_intelligence_chain() -> None:
    routing, intelligence, stopping, output, plan = _chain()

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.operation_id == routing.operation_id
    assert decision.context_digest == routing.context_digest
    assert decision.routing_context_digest == routing.receipt_digest
    assert decision.intelligence_quality_digest == intelligence.decision_digest
    assert decision.stopping_digest == stopping.decision_digest
    assert decision.output_quality_digest == output.decision_digest
    assert decision.plan_qualification_digest == plan.decision_digest
    assert decision.reasoning_policy_digest == stopping.policy_digest
    assert decision.planning_history_digest == stopping.history_digest
    assert len(decision.evidence_chain_digest) == 64
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "core_intelligence_qualification"
    assert evidence.digest == decision.decision_digest


def test_routing_blockers_fail_closed() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    routing = replace(
        routing,
        blockers=("route_not_successful",),
        eligible_for_promotion=False,
    )

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "routing-context-not-promotable" in decision.reasons
    assert "routing-context-blocked" in decision.reasons


def test_routing_quality_rejection_blocks() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    routing = replace(
        routing,
        quality_accepted=False,
        blockers=("quality_below_floor",),
        eligible_for_promotion=False,
    )

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "routing-context-quality-rejected" in decision.reasons


def test_memory_retrieval_quality_rejection_blocks() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    intelligence = replace(
        intelligence,
        accepted=False,
        reasons=("freshness-rejected",),
    )

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "intelligence-quality-rejected" in decision.reasons


def test_quality_report_substitution_blocks() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    intelligence = replace(intelligence, quality_digest="0" * 64)

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "quality-report-digest-mismatch" in decision.reasons


def test_reasoning_must_finish_complete() -> None:
    routing, intelligence, stopping, output, _ = _chain()
    stopping = replace(
        stopping,
        disposition=StopDisposition.CONTINUE,
        reason="more-work-needed",
    )
    plan = _plan(stopping)

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "reasoning-not-complete" in decision.reasons


def test_output_quality_rejection_blocks() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    output = replace(
        output,
        accepted=False,
        reasons=("answer-quality-rejected",),
    )

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "output-quality-rejected" in decision.reasons


def test_plan_rejection_blocks() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    plan = replace(
        plan,
        accepted=False,
        reasons=("simulation-rejected",),
    )

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "plan-qualification-rejected" in decision.reasons


def test_plan_must_bind_exact_stopping_decision() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    plan = replace(plan, stopping_digest="0" * 64)

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "plan-stopping-digest-mismatch" in decision.reasons


def test_plan_must_bind_exact_reasoning_policy() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    plan = replace(plan, reasoning_policy_digest="0" * 64)

    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    assert "reasoning-policy-digest-mismatch" in decision.reasons


def test_rejected_bundle_cannot_materialize_promotion_evidence() -> None:
    routing, intelligence, stopping, output, plan = _chain()
    plan = replace(
        plan,
        accepted=False,
        reasons=("simulation-rejected",),
    )
    decision = qualify_core_intelligence(
        routing_context=routing,
        intelligence_quality=intelligence,
        stopping=stopping,
        output_quality=output,
        plan_qualification=plan,
    )

    assert decision.accepted is False
    with pytest.raises(CoreIntelligenceError, match="cannot become promotion"):
        decision.accepted_evidence_ref()
