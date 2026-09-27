from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from skeleton.context.compiler import ContextCompiler
from skeleton.context.policy import ContextCompilePolicy
from skeleton.contracts.context import (
    ContextBudget,
    ContextKind,
    ContextSegment,
    ContextTrust,
)
from skeleton.frontier.model_routing import (
    ModelRouteRequest,
    ModelRouter,
    RouteBudget,
    RoutePlan,
)
from skeleton.frontier.model_runtime import (
    ChatResponse,
    ModelCapability,
    ModelMessage,
    TokenUsage,
)
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
    evaluate_admission,
)
from skeleton.intelligence.quality import QualityReport
from skeleton.intelligence.routing_context_receipt import (
    RoutingContextReceiptError,
    bind_route_request_to_context,
    build_routing_context_receipt,
)


OPERATION_ID = "11111111-1111-4111-8111-111111111111"
EXECUTION_ID = "22222222-2222-4222-8222-222222222222"
TURN_ID = "33333333-3333-4333-8333-333333333333"
TENANT_ID = "tenant-a"
PURPOSE = "answer"
NOW = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)


class FakeAdapter:
    name = "alpha"
    capabilities = frozenset({ModelCapability.CHAT})

    async def chat(self, request):
        return ChatResponse(
            model=request.model,
            text="bounded answer",
            usage=TokenUsage(input_tokens=12, output_tokens=7),
        )

    async def embed(self, request):
        raise AssertionError("routing-context tests must not call embed")

    async def stream_chat(self, request):
        if False:
            yield None
        raise AssertionError("routing-context tests must not stream")


def _budget() -> ContextBudget:
    return ContextBudget(
        max_context_tokens=2_000,
        reserved_output_tokens=200,
        reserved_tool_result_tokens=100,
        reserved_policy_tokens=100,
        safety_margin_tokens=100,
        max_segment_tokens=1_000,
        max_artifact_tokens=1_000,
        max_tool_result_tokens=1_000,
    )


def _segment(
    *,
    suffix: int,
    kind: ContextKind,
    source_type: str,
    content: str,
    trust: ContextTrust,
    data_class: str,
    tenant_id: str = TENANT_ID,
    purpose: str = PURPOSE,
    mandatory: bool = False,
) -> ContextSegment:
    segment_id = str(
        UUID(int=(0x44444444444444448444444444444440 + suffix))
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=kind,
        source_type=source_type,
        source_id=f"source-{suffix}",
        content=content,
        trust_level=trust,
        data_class=data_class,
        tenant_id=tenant_id,
        purpose=purpose,
        priority=100 - suffix,
        relevance=1.0,
        created_at=NOW,
        provenance=(f"fixture:{suffix}",),
        retention_class="session",
        mandatory=mandatory,
    )


def _context(
    *,
    purpose: str = PURPOSE,
    data_class: str = "confidential",
    policy: ContextCompilePolicy | None = None,
):
    compile_policy = policy or ContextCompilePolicy(max_data_class=data_class)
    segments = (
        _segment(
            suffix=1,
            kind=ContextKind.SYSTEM_POLICY,
            source_type="platform-policy",
            content="Follow platform policy.",
            trust=ContextTrust.TRUSTED_CONTROL,
            data_class="internal",
            tenant_id="*",
            purpose="*",
            mandatory=True,
        ),
        _segment(
            suffix=2,
            kind=ContextKind.USER_MESSAGE,
            source_type="conversation",
            content="Summarize the supplied evidence.",
            trust=ContextTrust.AUTHORIZED_USER_DATA,
            data_class=data_class,
            purpose=purpose,
        ),
    )
    return ContextCompiler(policy=compile_policy).compile(
        operation_id=OPERATION_ID,
        execution_id=EXECUTION_ID,
        turn_id=TURN_ID,
        tenant_id=TENANT_ID,
        purpose=purpose,
        budget=_budget(),
        segments=segments,
        tools_enabled=False,
        compiled_at=NOW,
    )


def _request() -> ModelRouteRequest:
    return ModelRouteRequest(
        request_id="route-1",
        messages=(ModelMessage("user", "Summarize."),),
        required_capabilities=frozenset({"chat"}),
        timeout_seconds=1.0,
        budget=RouteBudget(
            max_cost=1.0,
            max_output_tokens=100,
            max_provider_attempts=2,
        ),
        estimated_input_tokens=20,
        max_output_tokens=50,
        metadata={"caller": "test"},
    )


def _router() -> ModelRouter:
    router = ModelRouter()
    router.register(
        {
            "provider_id": "alpha",
            "adapter_name": "alpha",
            "model": "alpha-model",
            "capabilities": ("chat",),
            "max_input_tokens": 8_000,
            "max_output_tokens": 1_000,
            "input_cost_per_million": 1.0,
            "output_cost_per_million": 2.0,
            "timeout_seconds": 1.0,
            "priority": 1,
            "enabled": True,
            "max_attempts": 1,
            "backoff_seconds": 0.0,
        },
        FakeAdapter(),
    )
    return router


def _admission(context, *, max_cost_usd: float = 1.0):
    return evaluate_admission(
        AdmissionRequest(
            operation_id=OPERATION_ID,
            tenant_id=TENANT_ID,
            capability="model_route",
            budget=ResourceBudget(
                max_input_tokens=10_000,
                max_output_tokens=1_000,
                max_cost_usd=max_cost_usd,
                max_wall_seconds=5.0,
                max_provider_attempts=2,
            ),
            estimate=UsageEstimate(
                input_tokens=context.selected_tokens_estimate,
                output_tokens=50,
                cost_usd=0.001,
                wall_seconds=0.1,
                provider_attempts=1,
            ),
        )
    )


def _quality(*, accepted: bool = True, score: float = 0.93) -> QualityReport:
    return QualityReport(
        accepted=accepted,
        reason="measured_quality",
        score=score,
        thresholds={"minimum": 0.8},
        summary={"checks": 3},
        metadata={"evaluator": "offline-fixture"},
    )


def _joined(
    *,
    context=None,
    policy=None,
    quality=None,
    quality_floor: float = 0.8,
):
    context = context or _context()
    policy = policy or ContextCompilePolicy(max_data_class="confidential")
    request = bind_route_request_to_context(
        _request(),
        context,
        purpose=PURPOSE,
    )
    router = _router()
    plan = router.plan(request)
    result = asyncio.run(router.invoke(request))
    admission = _admission(context)
    receipt = build_routing_context_receipt(
        request,
        plan,
        result,
        context,
        admission,
        quality or _quality(),
        policy=policy,
        quality_floor=quality_floor,
    )
    return request, plan, result, admission, receipt


def test_joined_receipt_binds_quality_privacy_budget_and_route() -> None:
    _, _, _, _, receipt = _joined()

    assert receipt.eligible_for_promotion is True
    assert receipt.blockers == ()
    assert receipt.route_status == "ok"
    assert receipt.selected_provider_id == "alpha"
    assert receipt.required_capabilities == ("chat",)
    assert receipt.context_tokens <= receipt.context_capacity
    assert dict(receipt.trust_counts) == {
        "authorized_user_data": 1,
        "trusted_control": 1,
    }
    assert dict(receipt.data_class_counts) == {
        "confidential": 1,
        "internal": 1,
    }
    assert receipt.quality_score == pytest.approx(0.93)
    assert len(receipt.receipt_digest) == 64
    evidence = receipt.evidence_ref()
    assert evidence.digest == receipt.receipt_digest
    assert evidence.category == "routing_context_quality"


def test_binding_helper_uses_canonical_context_and_rejects_conflicts() -> None:
    context = _context()
    bound = bind_route_request_to_context(_request(), context, purpose=PURPOSE)

    assert bound.metadata["operation_id"] == OPERATION_ID
    assert bound.metadata["execution_id"] == EXECUTION_ID
    assert bound.metadata["turn_id"] == TURN_ID
    assert bound.metadata["tenant_id"] == TENANT_ID
    assert bound.metadata["context_id"] == context.context_id
    assert bound.metadata["context_digest"] == context.context_digest
    assert bound.metadata["context_compiler_version"] == context.compiler_version
    assert bound.metadata["purpose"] == PURPOSE
    assert bound.metadata["caller"] == "test"

    conflicting = replace(
        _request(),
        metadata={"operation_id": "other-operation"},
    )
    with pytest.raises(RoutingContextReceiptError, match="conflicts"):
        bind_route_request_to_context(conflicting, context, purpose=PURPOSE)


def test_receipt_identity_ignores_timing_jitter() -> None:
    request, plan, result, admission, first = _joined()
    jittered_attempts = tuple(
        replace(attempt, latency_ms=attempt.latency_ms + 937.25)
        for attempt in result.attempts
    )
    jittered = replace(result, attempts=jittered_attempts)
    second = build_routing_context_receipt(
        request,
        plan,
        jittered,
        _context(),
        admission,
        _quality(),
        policy=ContextCompilePolicy(max_data_class="confidential"),
        quality_floor=0.8,
    )

    assert first.observed_attempt_latency_seconds != second.observed_attempt_latency_seconds
    assert first.receipt_digest == second.receipt_digest
    assert first.identity_payload() == second.identity_payload()
    assert first.payload()["telemetry"] != second.payload()["telemetry"]


def test_quality_floor_and_quality_rejection_fail_closed() -> None:
    for report, floor, expected in (
        (_quality(score=0.60), 0.80, "quality_floor_not_met"),
        (_quality(accepted=False, score=0.95), 0.80, "quality_report_rejected"),
    ):
        _, _, _, _, receipt = _joined(
            quality=report,
            quality_floor=floor,
        )
        assert expected in receipt.blockers
        assert receipt.eligible_for_promotion is False
        with pytest.raises(RoutingContextReceiptError, match="cannot become"):
            receipt.evidence_ref()


def test_context_is_revalidated_against_receipt_purpose() -> None:
    context = _context(purpose="different-purpose")
    policy = ContextCompilePolicy(max_data_class="confidential")
    request = bind_route_request_to_context(_request(), context, purpose=PURPOSE)
    router = _router()
    plan = router.plan(request)
    result = asyncio.run(router.invoke(request))
    receipt = build_routing_context_receipt(
        request,
        plan,
        result,
        context,
        _admission(context),
        _quality(),
        policy=policy,
        quality_floor=0.8,
    )

    assert "context_privacy_or_policy_violation" in receipt.blockers
    assert receipt.eligible_for_promotion is False


def test_stricter_data_class_policy_blocks_previously_compiled_context() -> None:
    permissive = ContextCompilePolicy(max_data_class="restricted")
    context = _context(data_class="restricted", policy=permissive)
    strict = ContextCompilePolicy(max_data_class="confidential")
    request = bind_route_request_to_context(_request(), context, purpose=PURPOSE)
    router = _router()
    plan = router.plan(request)
    result = asyncio.run(router.invoke(request))
    receipt = build_routing_context_receipt(
        request,
        plan,
        result,
        context,
        _admission(context),
        _quality(),
        policy=strict,
        quality_floor=0.8,
    )

    assert receipt.max_selected_data_class == "restricted"
    assert receipt.max_allowed_data_class == "confidential"
    assert "context_privacy_or_policy_violation" in receipt.blockers


def test_route_plan_result_drift_is_rejected() -> None:
    context = _context()
    request = bind_route_request_to_context(_request(), context, purpose=PURPOSE)
    router = _router()
    result = asyncio.run(router.invoke(request))
    drifted_plan = RoutePlan(
        request_id=request.request_id,
        provider_ids=("ghost",),
        rejected={},
    )

    with pytest.raises(
        RoutingContextReceiptError,
        match="provider order mismatch",
    ):
        build_routing_context_receipt(
            request,
            drifted_plan,
            result,
            context,
            _admission(context),
            _quality(),
            policy=ContextCompilePolicy(max_data_class="confidential"),
            quality_floor=0.8,
        )


def test_successful_route_cannot_bypass_denied_admission() -> None:
    context = _context()
    request = bind_route_request_to_context(_request(), context, purpose=PURPOSE)
    router = _router()
    plan = router.plan(request)
    result = asyncio.run(router.invoke(request))
    denied = _admission(context, max_cost_usd=0.0)

    assert denied.admitted is False
    with pytest.raises(
        RoutingContextReceiptError,
        match="cannot bypass denied admission",
    ):
        build_routing_context_receipt(
            request,
            plan,
            result,
            context,
            denied,
            _quality(),
            policy=ContextCompilePolicy(max_data_class="confidential"),
            quality_floor=0.8,
        )


def test_receipt_payload_does_not_expose_prompt_or_context_text() -> None:
    _, _, _, _, receipt = _joined()
    rendered = repr(receipt.payload())

    assert "Follow platform policy." not in rendered
    assert "Summarize the supplied evidence." not in rendered
    assert "bounded answer" not in rendered
