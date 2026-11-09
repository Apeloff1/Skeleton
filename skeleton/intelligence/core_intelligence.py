"""P1 terminal core-intelligence qualification bundle.

This module is a non-executing join authority. It aggregates already accepted
routing/context, memory/retrieval/knowledge, reasoning/stopping, answer/artifact,
and plan-verification evidence into one deterministic P1-INTEL-06 receipt.

It cannot execute a plan, change model/provider state, or self-promote maturity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from skeleton.contracts.canonical import EvidenceRef
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


CORE_INTELLIGENCE_SCHEMA_VERSION = 1
CORE_INTELLIGENCE_TASK_ID = "P1-INTEL-06"
CORE_INTELLIGENCE_ACCOUNTABILITY_ID = "ACC-P1-INTEL-06"


class CoreIntelligenceError(ValueError):
    """Core-intelligence evidence cannot be joined safely."""


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoreIntelligenceError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise CoreIntelligenceError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise CoreIntelligenceError(f"{field} must be lowercase sha256")
    return text


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CoreIntelligenceError(
            "core-intelligence payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CoreIntelligenceQualification:
    accepted: bool
    reasons: tuple[str, ...]
    operation_id: str
    execution_id: str
    turn_id: str
    tenant_id: str
    request_id: str
    context_id: str
    context_digest: str
    routing_context_digest: str
    intelligence_quality_digest: str
    stopping_digest: str
    output_quality_digest: str
    plan_qualification_digest: str
    reasoning_policy_digest: str
    planning_history_digest: str
    task_id: str = CORE_INTELLIGENCE_TASK_ID
    accountability_id: str = CORE_INTELLIGENCE_ACCOUNTABILITY_ID
    schema_version: int = CORE_INTELLIGENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise CoreIntelligenceError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise CoreIntelligenceError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "operation_id",
            "execution_id",
            "turn_id",
            "tenant_id",
            "request_id",
            "context_id",
        ):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field),
            )
        for field in (
            "context_digest",
            "routing_context_digest",
            "intelligence_quality_digest",
            "stopping_digest",
            "output_quality_digest",
            "plan_qualification_digest",
            "reasoning_policy_digest",
            "planning_history_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.task_id != CORE_INTELLIGENCE_TASK_ID:
            raise CoreIntelligenceError("task_id drift")
        if self.accountability_id != CORE_INTELLIGENCE_ACCOUNTABILITY_ID:
            raise CoreIntelligenceError("accountability_id drift")
        if self.schema_version != CORE_INTELLIGENCE_SCHEMA_VERSION:
            raise CoreIntelligenceError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "tenant_id": self.tenant_id,
            "request_id": self.request_id,
            "context_id": self.context_id,
            "context_digest": self.context_digest,
            "routing_context_digest": self.routing_context_digest,
            "intelligence_quality_digest": self.intelligence_quality_digest,
            "stopping_digest": self.stopping_digest,
            "output_quality_digest": self.output_quality_digest,
            "plan_qualification_digest": self.plan_qualification_digest,
            "reasoning_policy_digest": self.reasoning_policy_digest,
            "planning_history_digest": self.planning_history_digest,
        }

    @property
    def evidence_chain_digest(self) -> str:
        return _canonical_digest(
            {
                "routing_context_digest": self.routing_context_digest,
                "intelligence_quality_digest": self.intelligence_quality_digest,
                "stopping_digest": self.stopping_digest,
                "output_quality_digest": self.output_quality_digest,
                "plan_qualification_digest": self.plan_qualification_digest,
                "reasoning_policy_digest": self.reasoning_policy_digest,
                "planning_history_digest": self.planning_history_digest,
            }
        )

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(
            {
                **self.payload(),
                "evidence_chain_digest": self.evidence_chain_digest,
            }
        )

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:intel-06:core-intelligence-bundle",
    ) -> EvidenceRef:
        if not self.accepted:
            raise CoreIntelligenceError(
                "rejected core-intelligence bundle cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="core_intelligence_qualification",
        )


def qualify_core_intelligence(
    *,
    routing_context: RoutingContextReceipt,
    intelligence_quality: IntelligenceQualityDecision,
    stopping: StoppingDecision,
    output_quality: AnswerArtifactQualityDecision,
    plan_qualification: PlanQualificationDecision,
) -> CoreIntelligenceQualification:
    """Join accepted P1 core-intelligence decisions fail closed."""

    if not isinstance(routing_context, RoutingContextReceipt):
        raise TypeError("routing_context must be RoutingContextReceipt")
    if not isinstance(intelligence_quality, IntelligenceQualityDecision):
        raise TypeError(
            "intelligence_quality must be IntelligenceQualityDecision"
        )
    if not isinstance(stopping, StoppingDecision):
        raise TypeError("stopping must be StoppingDecision")
    if not isinstance(output_quality, AnswerArtifactQualityDecision):
        raise TypeError(
            "output_quality must be AnswerArtifactQualityDecision"
        )
    if not isinstance(plan_qualification, PlanQualificationDecision):
        raise TypeError(
            "plan_qualification must be PlanQualificationDecision"
        )

    reasons: list[str] = []

    if not routing_context.eligible_for_promotion:
        reasons.append("routing-context-not-promotable")
    if not routing_context.quality_accepted:
        reasons.append("routing-context-quality-rejected")
    if routing_context.blockers:
        reasons.append("routing-context-blocked")

    if not intelligence_quality.accepted:
        reasons.append("intelligence-quality-rejected")
    if routing_context.quality_digest != intelligence_quality.quality_digest:
        reasons.append("quality-report-digest-mismatch")

    if stopping.disposition is not StopDisposition.COMPLETE:
        reasons.append("reasoning-not-complete")

    if not output_quality.accepted:
        reasons.append("output-quality-rejected")

    if not plan_qualification.accepted:
        reasons.append("plan-qualification-rejected")
    if plan_qualification.stopping_digest != stopping.decision_digest:
        reasons.append("plan-stopping-digest-mismatch")
    if plan_qualification.reasoning_policy_digest != stopping.policy_digest:
        reasons.append("reasoning-policy-digest-mismatch")

    normalized = tuple(sorted(set(reasons)))
    return CoreIntelligenceQualification(
        accepted=not normalized,
        reasons=normalized,
        operation_id=routing_context.operation_id,
        execution_id=routing_context.execution_id,
        turn_id=routing_context.turn_id,
        tenant_id=routing_context.tenant_id,
        request_id=routing_context.request_id,
        context_id=routing_context.context_id,
        context_digest=routing_context.context_digest,
        routing_context_digest=routing_context.receipt_digest,
        intelligence_quality_digest=intelligence_quality.decision_digest,
        stopping_digest=stopping.decision_digest,
        output_quality_digest=output_quality.decision_digest,
        plan_qualification_digest=plan_qualification.decision_digest,
        reasoning_policy_digest=stopping.policy_digest,
        planning_history_digest=stopping.history_digest,
    )


__all__ = [
    "CORE_INTELLIGENCE_ACCOUNTABILITY_ID",
    "CORE_INTELLIGENCE_SCHEMA_VERSION",
    "CORE_INTELLIGENCE_TASK_ID",
    "CoreIntelligenceError",
    "CoreIntelligenceQualification",
    "qualify_core_intelligence",
]
