"""Canonical routing/context quality receipt for P1 core-intelligence evidence.

The receipt joins already-authoritative runtime decisions. It does not select a
provider, compile context, admit work, score quality, or promote maturity.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Any

from skeleton.context.policy import ContextCompilePolicy
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.context import ContextEnvelope
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.model_routing import (
    ModelRouteRequest,
    ModelRouteResult,
    RoutePlan,
)
from skeleton.intelligence.admission import (
    AdmissionDecision,
    AdmissionStatus,
)
from skeleton.intelligence.quality import QualityReport


ROUTING_CONTEXT_RECEIPT_SCHEMA_VERSION = 1
ROUTING_CONTEXT_TASK_ID = "P1-INTEL-01"
ROUTING_CONTEXT_ACCOUNTABILITY_ID = "ACC-P1-INTEL-01"

_DATA_CLASS_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


class RoutingContextReceiptError(ValueError):
    """Runtime decisions cannot be joined into one trustworthy receipt."""


def _finite_unit(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RoutingContextReceiptError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise RoutingContextReceiptError(f"{field} must be within [0, 1]")
    return number


def _required_metadata(request: ModelRouteRequest, key: str) -> str:
    value = request.metadata.get(key)
    if not isinstance(value, str) or not value:
        raise RoutingContextReceiptError(
            f"route request metadata must bind {key}"
        )
    return value


def _message_digest(request: ModelRouteRequest) -> str:
    rows = []
    for message in request.messages:
        rows.append(
            {
                "role": getattr(message, "role", ""),
                "content_digest": stable_content_digest(
                    getattr(message, "content", "")
                ),
            }
        )
    return stable_content_digest(rows)


def _request_digest(request: ModelRouteRequest) -> str:
    return stable_content_digest(
        {
            "request_id": request.request_id,
            "messages_digest": _message_digest(request),
            "required_capabilities": sorted(request.required_capabilities),
            "tools_digest": stable_content_digest(
                [repr(item) for item in request.tools]
            ),
            "response_schema_digest": (
                None
                if request.response_schema is None
                else stable_content_digest(dict(request.response_schema))
            ),
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "timeout_seconds": request.timeout_seconds,
            "retry_policy": repr(request.retry_policy),
            "budget": {
                "max_cost": request.budget.max_cost,
                "max_output_tokens": request.budget.max_output_tokens,
                "max_provider_attempts": request.budget.max_provider_attempts,
            },
            "estimated_input_tokens": request.estimated_input_tokens,
            "context_id": request.metadata.get("context_id"),
            "context_digest": request.metadata.get("context_digest"),
            "operation_id": request.metadata.get("operation_id"),
            "tenant_id": request.metadata.get("tenant_id"),
        }
    )


def _result_digest(result: ModelRouteResult) -> str:
    response = result.response
    provenance = result.provenance
    return stable_content_digest(
        {
            "request_id": result.request_id,
            "status": result.status,
            "selected_provider_id": result.selected_provider_id,
            "planned_provider_ids": list(result.planned_provider_ids),
            "fallback_provider_ids": list(result.fallback_provider_ids),
            "response": (
                None
                if response is None
                else {
                    "model": response.model,
                    "text_digest": stable_content_digest(response.text),
                    "finish_reason": response.finish_reason,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                }
            ),
            "attempts": [attempt.as_dict() for attempt in result.attempts],
            "provenance": {
                "source_repository": provenance.source_repository,
                "source_revision": provenance.source_revision,
                "source_path": provenance.source_path,
                "operation": provenance.operation,
                "actor": provenance.actor,
                "content_sha256": provenance.content_sha256,
                "metadata": dict(provenance.metadata),
            },
            "budget": result.budget.as_dict(),
        }
    )


def _summary_pairs(values: Counter[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((key, int(value)) for key, value in values.items()))


@dataclass(frozen=True, slots=True)
class RoutingContextReceipt:
    operation_id: str
    execution_id: str
    turn_id: str
    tenant_id: str
    request_id: str
    context_id: str
    context_digest: str
    request_digest: str
    route_plan_digest: str
    route_result_digest: str
    admission_decision_id: str
    admission_status: str
    admission_reason: str
    route_status: str
    selected_provider_id: str | None
    planned_provider_ids: tuple[str, ...]
    fallback_provider_ids: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    context_tokens: int
    context_capacity: int
    trust_counts: tuple[tuple[str, int], ...]
    data_class_counts: tuple[tuple[str, int], ...]
    omission_reason_counts: tuple[tuple[str, int], ...]
    max_selected_data_class: str
    max_allowed_data_class: str
    quality_score: float
    quality_floor: float
    quality_accepted: bool
    quality_digest: str
    spent_cost: float
    remaining_cost: float | None
    spent_output_tokens: int
    remaining_output_tokens: int | None
    deadline_seconds: float
    observed_attempt_latency_seconds: float
    blockers: tuple[str, ...]
    eligible_for_promotion: bool
    task_id: str = ROUTING_CONTEXT_TASK_ID
    accountability_id: str = ROUTING_CONTEXT_ACCOUNTABILITY_ID
    schema_version: int = ROUTING_CONTEXT_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ROUTING_CONTEXT_RECEIPT_SCHEMA_VERSION:
            raise RoutingContextReceiptError("unsupported receipt schema version")
        if self.task_id != ROUTING_CONTEXT_TASK_ID:
            raise RoutingContextReceiptError("task_id drift")
        if self.accountability_id != ROUTING_CONTEXT_ACCOUNTABILITY_ID:
            raise RoutingContextReceiptError("accountability_id drift")
        if self.eligible_for_promotion != (not self.blockers):
            raise RoutingContextReceiptError(
                "promotion eligibility must be derived from blockers"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "tenant_id": self.tenant_id,
            "request_id": self.request_id,
            "context_id": self.context_id,
            "context_digest": self.context_digest,
            "request_digest": self.request_digest,
            "route_plan_digest": self.route_plan_digest,
            "route_result_digest": self.route_result_digest,
            "admission": {
                "decision_id": self.admission_decision_id,
                "status": self.admission_status,
                "reason": self.admission_reason,
            },
            "routing": {
                "status": self.route_status,
                "selected_provider_id": self.selected_provider_id,
                "planned_provider_ids": list(self.planned_provider_ids),
                "fallback_provider_ids": list(self.fallback_provider_ids),
                "required_capabilities": list(self.required_capabilities),
            },
            "context": {
                "selected_tokens": self.context_tokens,
                "input_capacity": self.context_capacity,
                "trust_counts": dict(self.trust_counts),
                "data_class_counts": dict(self.data_class_counts),
                "omission_reason_counts": dict(self.omission_reason_counts),
                "max_selected_data_class": self.max_selected_data_class,
                "max_allowed_data_class": self.max_allowed_data_class,
            },
            "quality": {
                "score": self.quality_score,
                "floor": self.quality_floor,
                "accepted": self.quality_accepted,
                "digest": self.quality_digest,
            },
            "budget": {
                "spent_cost": self.spent_cost,
                "remaining_cost": self.remaining_cost,
                "spent_output_tokens": self.spent_output_tokens,
                "remaining_output_tokens": self.remaining_output_tokens,
            },
            "deadline": {
                "seconds": self.deadline_seconds,
                "observed_attempt_latency_seconds": (
                    self.observed_attempt_latency_seconds
                ),
            },
            "blockers": list(self.blockers),
            "eligible_for_promotion": self.eligible_for_promotion,
        }

    @property
    def receipt_digest(self) -> str:
        return stable_content_digest(self.payload())

    def evidence_ref(self) -> EvidenceRef:
        if not self.eligible_for_promotion:
            raise RoutingContextReceiptError(
                "blocked routing/context receipt cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:routing-context:{self.request_id}",
            digest=self.receipt_digest,
            category="routing_context_quality",
        )


def build_routing_context_receipt(
    request: ModelRouteRequest,
    plan: RoutePlan,
    result: ModelRouteResult,
    context: ContextEnvelope,
    admission: AdmissionDecision,
    quality: QualityReport,
    *,
    policy: ContextCompilePolicy,
    quality_floor: float,
) -> RoutingContextReceipt:
    """Join canonical runtime decisions without mutating any authority."""

    if not isinstance(request, ModelRouteRequest):
        raise TypeError("request must be ModelRouteRequest")
    if not isinstance(plan, RoutePlan):
        raise TypeError("plan must be RoutePlan")
    if not isinstance(result, ModelRouteResult):
        raise TypeError("result must be ModelRouteResult")
    if not isinstance(context, ContextEnvelope):
        raise TypeError("context must be ContextEnvelope")
    if not isinstance(admission, AdmissionDecision):
        raise TypeError("admission must be AdmissionDecision")
    if not isinstance(quality, QualityReport):
        raise TypeError("quality must be QualityReport")
    if not isinstance(policy, ContextCompilePolicy):
        raise TypeError("policy must be ContextCompilePolicy")

    floor = _finite_unit(quality_floor, "quality_floor")
    score = _finite_unit(quality.score, "quality.score")

    if request.request_id != plan.request_id or request.request_id != result.request_id:
        raise RoutingContextReceiptError("route request/plan/result identity mismatch")
    if tuple(plan.provider_ids) != tuple(result.planned_provider_ids):
        raise RoutingContextReceiptError("route plan/result provider order mismatch")
    if tuple(plan.fallback_provider_ids) != tuple(result.fallback_provider_ids):
        raise RoutingContextReceiptError("route fallback order mismatch")
    if (
        result.selected_provider_id is not None
        and result.selected_provider_id not in plan.provider_ids
    ):
        raise RoutingContextReceiptError("selected provider was not in route plan")

    bound_operation = _required_metadata(request, "operation_id")
    bound_tenant = _required_metadata(request, "tenant_id")
    bound_context_id = _required_metadata(request, "context_id")
    bound_context_digest = _required_metadata(request, "context_digest")
    if bound_operation != context.operation_id:
        raise RoutingContextReceiptError("route/context operation mismatch")
    if bound_tenant != context.tenant_id:
        raise RoutingContextReceiptError("route/context tenant mismatch")
    if bound_context_id != context.context_id:
        raise RoutingContextReceiptError("route/context id mismatch")
    if bound_context_digest != context.context_digest:
        raise RoutingContextReceiptError("route/context digest mismatch")
    if admission.operation_id != context.operation_id:
        raise RoutingContextReceiptError("admission/context operation mismatch")
    if admission.tenant_id != context.tenant_id:
        raise RoutingContextReceiptError("admission/context tenant mismatch")
    if result.ok and admission.status is not AdmissionStatus.ADMIT:
        raise RoutingContextReceiptError(
            "successful route cannot bypass denied admission"
        )

    trust = Counter[str]()
    classes = Counter[str]()
    privacy_violation = False
    for segment in context.selected_segments:
        trust[segment.trust_level.value] += 1
        classes[segment.data_class] += 1
        inspected = policy.inspect(
            segment,
            tenant_id=context.tenant_id,
            purpose=segment.purpose,
        )
        if not inspected.allowed:
            privacy_violation = True

    max_selected = max(
        classes,
        key=lambda item: _DATA_CLASS_RANK[item],
        default="public",
    )
    if _DATA_CLASS_RANK[max_selected] > _DATA_CLASS_RANK[policy.max_data_class]:
        privacy_violation = True

    omission_counts = Counter(reason for _, reason in context.omission_reasons)
    context_capacity = context.budget.input_capacity(
        tools_enabled=bool(context.tool_schema_segments)
    )

    blockers: list[str] = []
    if admission.status is not AdmissionStatus.ADMIT:
        blockers.append("admission_not_admitted")
    if result.status != "ok":
        blockers.append("route_not_successful")
    if result.status == "ok" and result.selected_provider_id is None:
        blockers.append("successful_route_missing_provider")
    if privacy_violation:
        blockers.append("context_privacy_or_policy_violation")
    if context.selected_tokens_estimate > context_capacity:
        blockers.append("context_budget_exceeded")
    if not quality.accepted:
        blockers.append("quality_report_rejected")
    if score < floor:
        blockers.append("quality_floor_not_met")
    if result.provenance.content_sha256 is None:
        blockers.append("route_provenance_missing")

    if (
        request.budget.max_cost is not None
        and result.budget.spent_cost > request.budget.max_cost + 1e-12
    ):
        blockers.append("route_cost_budget_exceeded")
    if (
        request.budget.max_output_tokens is not None
        and result.budget.spent_output_tokens > request.budget.max_output_tokens
    ):
        blockers.append("route_output_budget_exceeded")

    observed_latency = sum(
        max(0.0, float(attempt.latency_ms)) for attempt in result.attempts
    ) / 1000.0
    if observed_latency > request.timeout_seconds + 1e-9:
        blockers.append("route_deadline_exceeded")

    unique_blockers = tuple(sorted(set(blockers)))
    return RoutingContextReceipt(
        operation_id=context.operation_id,
        execution_id=context.execution_id,
        turn_id=context.turn_id,
        tenant_id=context.tenant_id,
        request_id=request.request_id,
        context_id=context.context_id,
        context_digest=context.context_digest,
        request_digest=_request_digest(request),
        route_plan_digest=stable_content_digest(plan.as_dict()),
        route_result_digest=_result_digest(result),
        admission_decision_id=admission.decision_id,
        admission_status=admission.status.value,
        admission_reason=admission.reason_code,
        route_status=result.status,
        selected_provider_id=result.selected_provider_id,
        planned_provider_ids=tuple(result.planned_provider_ids),
        fallback_provider_ids=tuple(result.fallback_provider_ids),
        required_capabilities=tuple(sorted(request.required_capabilities)),
        context_tokens=context.selected_tokens_estimate,
        context_capacity=context_capacity,
        trust_counts=_summary_pairs(trust),
        data_class_counts=_summary_pairs(classes),
        omission_reason_counts=_summary_pairs(omission_counts),
        max_selected_data_class=max_selected,
        max_allowed_data_class=policy.max_data_class,
        quality_score=score,
        quality_floor=floor,
        quality_accepted=bool(quality.accepted),
        quality_digest=stable_content_digest(quality.to_dict()),
        spent_cost=float(result.budget.spent_cost),
        remaining_cost=result.budget.remaining_cost,
        spent_output_tokens=result.budget.spent_output_tokens,
        remaining_output_tokens=result.budget.remaining_output_tokens,
        deadline_seconds=float(request.timeout_seconds),
        observed_attempt_latency_seconds=observed_latency,
        blockers=unique_blockers,
        eligible_for_promotion=not unique_blockers,
    )


__all__ = [
    "ROUTING_CONTEXT_ACCOUNTABILITY_ID",
    "ROUTING_CONTEXT_RECEIPT_SCHEMA_VERSION",
    "ROUTING_CONTEXT_TASK_ID",
    "RoutingContextReceipt",
    "RoutingContextReceiptError",
    "build_routing_context_receipt",
]
