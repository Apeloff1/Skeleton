"""Pure cost-governor policy, digests, and payload codecs.

The governor runtime and its SQLite journal stay in ``cost_governor``.
This module is the part that can be read without opening the journal.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.quota import (
    QuotaCompletion,
    QuotaReservation,
    QuotaUsageEvent,
)


_SAFE_FALLBACK_REASON_PREFIXES = (
    "input_token_budget_exceeded",
    "output_token_budget_exceeded",
    "cost_budget_exceeded",
    "wall_time_budget_exceeded",
    "provider_attempt_budget_exceeded",
    "tool_call_budget_exceeded",
    "artifact_budget_exceeded",
    "storage_budget_exceeded",
    "tenant_quota_exceeded:",
)
_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "wall_seconds",
    "provider_attempts",
    "tool_calls",
    "artifact_bytes",
    "storage_bytes",
)


class CostGovernorError(RuntimeError):
    """The cost-governor contract or integrated runtime transition failed."""


class CostGovernorDenied(CostGovernorError):
    """The requested or fallback work was denied by a governed budget."""


class CostGovernorConflict(CostGovernorError):
    """An idempotency, lease, or durable accounting conflict occurred."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CostGovernorError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise CostGovernorError(f"{name} exceeds maximum length")
    return value


def _sha256(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CostGovernorError(f"{name} must be lowercase sha256")
    return value


def _canonical_json_text(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CostGovernorError(
            "cost-governor evidence must be canonical JSON"
        ) from exc


def _canonical_digest(value: object) -> str:
    raw = _canonical_json_text(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _usage_payload(usage: UsageEstimate) -> dict[str, int | float]:
    if not isinstance(usage, UsageEstimate):
        raise TypeError("usage must be UsageEstimate")
    return {
        field: getattr(usage, field)
        for field in _USAGE_FIELDS
    }


def _usage_from_payload(value: object) -> UsageEstimate:
    if not isinstance(value, dict):
        raise CostGovernorError("usage journal payload is invalid")
    try:
        return UsageEstimate(
            input_tokens=int(value["input_tokens"]),
            output_tokens=int(value["output_tokens"]),
            cost_usd=float(value["cost_usd"]),
            wall_seconds=float(value["wall_seconds"]),
            provider_attempts=int(value["provider_attempts"]),
            tool_calls=int(value["tool_calls"]),
            artifact_bytes=int(value["artifact_bytes"]),
            storage_bytes=int(value["storage_bytes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "usage journal payload is invalid"
        ) from exc


def _budget_from_payload(value: object) -> ResourceBudget:
    if not isinstance(value, dict):
        raise CostGovernorError("budget journal payload is invalid")
    try:
        return ResourceBudget(
            max_input_tokens=int(value["max_input_tokens"]),
            max_output_tokens=int(value["max_output_tokens"]),
            max_cost_usd=float(value["max_cost_usd"]),
            max_wall_seconds=float(value["max_wall_seconds"]),
            max_provider_attempts=int(value["max_provider_attempts"]),
            max_tool_calls=int(value["max_tool_calls"]),
            max_artifact_bytes=int(value["max_artifact_bytes"]),
            max_storage_bytes=int(value["max_storage_bytes"]),
            max_concurrency=int(value["max_concurrency"]),
            max_queue_depth=int(value["max_queue_depth"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "budget journal payload is invalid"
        ) from exc


def _effective_terminal_actual(
    reported: UsageEstimate,
    completion: QuotaCompletion,
) -> UsageEstimate:
    observed = completion.actual
    return UsageEstimate(
        input_tokens=max(reported.input_tokens, observed.input_tokens),
        output_tokens=max(reported.output_tokens, observed.output_tokens),
        cost_usd=max(reported.cost_usd, observed.cost_usd),
        wall_seconds=reported.wall_seconds,
        provider_attempts=reported.provider_attempts,
        tool_calls=max(reported.tool_calls, observed.tool_calls),
        artifact_bytes=max(
            reported.artifact_bytes,
            observed.artifact_bytes,
        ),
        storage_bytes=max(
            reported.storage_bytes,
            observed.storage_bytes,
        ),
    )


def _budget_overrun_dimensions(
    budget: ResourceBudget,
    actual: UsageEstimate,
) -> tuple[str, ...]:
    limits: dict[str, int | float] = {
        "input_tokens": budget.max_input_tokens,
        "output_tokens": budget.max_output_tokens,
        "cost_usd": budget.max_cost_usd,
        "wall_seconds": budget.max_wall_seconds,
        "provider_attempts": budget.max_provider_attempts,
        "tool_calls": budget.max_tool_calls,
        "artifact_bytes": budget.max_artifact_bytes,
        "storage_bytes": budget.max_storage_bytes,
    }
    exceeded: list[str] = []
    for field, limit in limits.items():
        value = getattr(actual, field)
        if field in {"cost_usd", "wall_seconds"}:
            if float(value) > float(limit) + 1e-12:
                exceeded.append(field)
        elif int(value) > int(limit):
            exceeded.append(field)
    return tuple(exceeded)


def _request_digest(request: AdmissionRequest) -> str:
    if not isinstance(request, AdmissionRequest):
        raise TypeError("request must be AdmissionRequest")
    return _canonical_digest(
        {
            "operation_id": request.operation_id,
            "tenant_id": request.tenant_id,
            "capability": request.capability,
            "budget": request.budget.as_dict(),
            "estimate": _usage_payload(request.estimate),
            "priority": request.priority,
            "deadline_monotonic": request.deadline_monotonic,
        }
    )


def _quota_reservation_digest(reservation: QuotaReservation | None) -> str | None:
    if reservation is None:
        return None
    return _canonical_digest(reservation.as_dict())


def _usage_event_digest(event: QuotaUsageEvent) -> str:
    return _canonical_digest(event.as_dict())


def _completion_digest(completion: QuotaCompletion | None) -> str | None:
    if completion is None:
        return None
    return _canonical_digest(completion.as_dict())


def _fallback_reason_allowed(reason: str, allowed: tuple[str, ...]) -> bool:
    return any(
        reason == prefix or reason.startswith(prefix)
        for prefix in allowed
    )


def _validated_evidence_refs(
    values: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise CostGovernorError(
            "evidence_refs must contain EvidenceRef values"
        )
    refs = tuple(values)
    if not refs:
        raise CostGovernorError("evidence_refs must be non-empty")
    normalized: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in refs:
        if not isinstance(item, EvidenceRef):
            raise CostGovernorError(
                "evidence_refs must contain EvidenceRef values"
            )
        source = _token("evidence source", item.source)
        digest = _sha256("evidence digest", item.digest)
        category = _token("evidence category", item.category)
        normalized[(source, digest, category)] = item
    return tuple(normalized[key] for key in sorted(normalized))


def _strictly_cheaper(
    requested: UsageEstimate,
    fallback: UsageEstimate,
) -> bool:
    less = False
    for field in _USAGE_FIELDS:
        before = getattr(requested, field)
        after = getattr(fallback, field)
        if after > before:
            return False
        if after < before:
            less = True
    return less
