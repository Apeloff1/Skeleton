"""Execution semantics for the canonical internal protocol envelope.

The schema and message identity authority lives in skeleton.contracts.protocol.
This module deliberately does not define another ProtocolEnvelope. It binds the
canonical contract to bounded delivery attempts, tenant/authority identity,
causal child creation, trace-safe evidence, and receipts.

VOL-131 invariants:
- one canonical envelope authority;
- retries preserve payload, operation, correlation, tenant, authority and
  deadline identity while advancing only message/span/attempt identity;
- retry attempts are bounded and predecessor-digest chained;
- children preserve operation/correlation/trace lineage and cannot widen the
  parent's deadline or authority;
- trace records expose identifiers and digests, never raw payload;
- receipts bind both the canonical envelope digest and the execution wrapper.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.protocol import (
    ProtocolEnvelope,
    RetryClass,
    UnknownOutcomePolicy,
)


INTERNAL_PROTOCOL_EXECUTION_VERSION = 2
VOL_131_ID = "VOL-131"
MAX_ATTRIBUTES = 32
MAX_ATTRIBUTE_KEY_CHARS = 64
MAX_ATTRIBUTE_VALUE_CHARS = 256
MAX_REASON_CHARS = 1024
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProtocolExecutionError(ValueError):
    """Execution metadata is malformed, ambiguous, or unsafe."""


class ProtocolOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


def _text(value: object, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolExecutionError(f"{field} must be a non-empty string")
    if value != value.strip() or len(value) > maximum:
        raise ProtocolExecutionError(f"{field} must be normalized and bounded")
    return value


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise ProtocolExecutionError(f"{field} must be a canonical token")
    return text


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ProtocolExecutionError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ProtocolExecutionError(f"{field} must be a positive integer")
    return value


def _timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtocolExecutionError(f"{field} must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProtocolExecutionError(f"{field} is invalid RFC3339 UTC") from exc
    if parsed.tzinfo is None:
        raise ProtocolExecutionError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_dt(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _pairs(
    values: Mapping[str, str] | Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    normalized: dict[str, str] = {}
    for key, value in items:
        normalized_key = _token(
            key,
            "attributes.key",
            maximum=MAX_ATTRIBUTE_KEY_CHARS,
        )
        if normalized_key in normalized:
            raise ProtocolExecutionError(
                f"attributes contains duplicate key: {normalized_key}"
            )
        normalized[normalized_key] = _text(
            value,
            "attributes.value",
            maximum=MAX_ATTRIBUTE_VALUE_CHARS,
        )
    if len(normalized) > MAX_ATTRIBUTES:
        raise ProtocolExecutionError("attributes exceeds item limit")
    return tuple(sorted(normalized.items()))


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolExecutionError(
            "protocol execution identity must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ProtocolExecutionEnvelope:
    """Bounded execution metadata for one canonical ProtocolEnvelope."""

    envelope: ProtocolEnvelope
    tenant_id: str
    authority_digest: str
    issued_at_utc: str
    max_attempts: int = 1
    previous_execution_digest: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    execution_version: int = INTERNAL_PROTOCOL_EXECUTION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, ProtocolEnvelope):
            raise ProtocolExecutionError(
                "envelope must be canonical skeleton.contracts ProtocolEnvelope"
            )
        object.__setattr__(self, "tenant_id", _token(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "authority_digest",
            _sha256(self.authority_digest, "authority_digest"),
        )
        issued = _timestamp(self.issued_at_utc, "issued_at_utc")
        object.__setattr__(self, "issued_at_utc", issued)
        max_attempts = _positive_int(self.max_attempts, "max_attempts")
        object.__setattr__(self, "max_attempts", max_attempts)
        object.__setattr__(self, "attributes", _pairs(self.attributes))

        if self.execution_version != INTERNAL_PROTOCOL_EXECUTION_VERSION:
            raise ProtocolExecutionError("unsupported protocol execution version")
        if self.envelope.attempt > max_attempts:
            raise ProtocolExecutionError(
                "canonical attempt cannot exceed execution max_attempts"
            )
        if self.envelope.deadline_utc is not None:
            if _timestamp_dt(issued) >= _timestamp_dt(self.envelope.deadline_utc):
                raise ProtocolExecutionError(
                    "issued_at_utc must precede canonical deadline"
                )

        if self.envelope.retry_class is RetryClass.NEVER:
            if max_attempts != 1 or self.envelope.attempt != 1:
                raise ProtocolExecutionError(
                    "RetryClass.NEVER requires one execution attempt"
                )
            if self.previous_execution_digest is not None:
                raise ProtocolExecutionError(
                    "non-retryable execution cannot bind predecessor"
                )
        else:
            if max_attempts < 2:
                raise ProtocolExecutionError(
                    "retryable execution requires max_attempts >= 2"
                )
            if self.envelope.deadline_utc is None:
                raise ProtocolExecutionError(
                    "retryable execution requires canonical deadline"
                )

        if self.previous_execution_digest is not None:
            object.__setattr__(
                self,
                "previous_execution_digest",
                _sha256(
                    self.previous_execution_digest,
                    "previous_execution_digest",
                ),
            )
        if self.envelope.attempt == 1 and self.previous_execution_digest is not None:
            raise ProtocolExecutionError(
                "first execution attempt cannot bind predecessor"
            )
        if self.envelope.attempt > 1:
            if self.previous_execution_digest is None:
                raise ProtocolExecutionError(
                    "retry attempt must bind previous_execution_digest"
                )
            if not self.envelope.causation_id:
                raise ProtocolExecutionError(
                    "retry attempt must bind canonical causation_id"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "execution_version": self.execution_version,
            "volume": VOL_131_ID,
            "canonical_envelope_digest": self.envelope.digest,
            "message_id": self.envelope.message_id,
            "operation_id": self.envelope.operation_id,
            "correlation_id": self.envelope.correlation_id,
            "causation_id": self.envelope.causation_id or None,
            "trace_id": self.envelope.trace_id,
            "span_id": self.envelope.span_id or None,
            "tenant_id": self.tenant_id,
            "authority_digest": self.authority_digest,
            "issued_at_utc": self.issued_at_utc,
            "deadline_utc": self.envelope.deadline_utc,
            "attempt": self.envelope.attempt,
            "max_attempts": self.max_attempts,
            "retry_class": self.envelope.retry_class.value,
            "unknown_outcome_policy": self.envelope.unknown_outcome_policy.value,
            "previous_execution_digest": self.previous_execution_digest,
            "attributes": [list(item) for item in self.attributes],
        }

    @property
    def execution_digest(self) -> str:
        return _canonical_digest(self.payload())

    def expired(self, *, now: datetime | None = None) -> bool:
        return self.envelope.deadline_exceeded(now=now)

    def retry(
        self,
        *,
        message_id: str,
        span_id: str,
        issued_at_utc: str,
    ) -> "ProtocolExecutionEnvelope":
        if self.envelope.retry_class is RetryClass.NEVER:
            raise ProtocolExecutionError("canonical envelope is not retryable")
        if self.envelope.attempt >= self.max_attempts:
            raise ProtocolExecutionError("retry attempt budget exhausted")
        issued = _timestamp(issued_at_utc, "issued_at_utc")
        if self.envelope.deadline_utc is None:
            raise ProtocolExecutionError("retryable envelope lost deadline")
        if _timestamp_dt(issued) >= _timestamp_dt(self.envelope.deadline_utc):
            raise ProtocolExecutionError("cannot retry expired envelope")

        next_envelope = replace(
            self.envelope,
            message_id=_token(message_id, "message_id"),
            causation_id=self.envelope.message_id,
            span_id=_token(span_id, "span_id"),
            attempt=self.envelope.attempt + 1,
        )
        return ProtocolExecutionEnvelope(
            envelope=next_envelope,
            tenant_id=self.tenant_id,
            authority_digest=self.authority_digest,
            issued_at_utc=issued,
            max_attempts=self.max_attempts,
            previous_execution_digest=self.execution_digest,
            attributes=self.attributes,
        )

    def spawn_child(
        self,
        *,
        message_id: str,
        span_id: str,
        recipient: str,
        kind: str,
        payload: Mapping[str, object],
        issued_at_utc: str,
        retry_class: RetryClass = RetryClass.NEVER,
        unknown_outcome_policy: UnknownOutcomePolicy = (
            UnknownOutcomePolicy.FAIL_CLOSED
        ),
        idempotency_key: str | None = None,
        max_attempts: int = 1,
        attributes: Mapping[str, str] | Iterable[tuple[str, str]] = (),
    ) -> "ProtocolExecutionEnvelope":
        issued = _timestamp(issued_at_utc, "issued_at_utc")
        if self.envelope.deadline_utc is not None:
            if _timestamp_dt(issued) >= _timestamp_dt(self.envelope.deadline_utc):
                raise ProtocolExecutionError(
                    "cannot spawn child after parent deadline"
                )
        child_key = (
            self.envelope.idempotency_key
            if idempotency_key is None
            else _token(idempotency_key, "idempotency_key", maximum=256)
        )
        child = ProtocolEnvelope(
            protocol=self.envelope.protocol,
            message_id=_token(message_id, "message_id"),
            kind=_token(kind, "kind"),
            sender=self.envelope.recipient,
            recipient=_token(recipient, "recipient"),
            operation_id=self.envelope.operation_id,
            correlation_id=self.envelope.correlation_id,
            causation_id=self.envelope.message_id,
            trace_id=self.envelope.trace_id,
            span_id=_token(span_id, "span_id"),
            deadline_utc=self.envelope.deadline_utc,
            idempotency_key=child_key,
            attempt=1,
            retry_class=retry_class,
            unknown_outcome_policy=unknown_outcome_policy,
            payload=payload,
        )
        return ProtocolExecutionEnvelope(
            envelope=child,
            tenant_id=self.tenant_id,
            authority_digest=self.authority_digest,
            issued_at_utc=issued,
            max_attempts=max_attempts,
            attributes=_pairs(attributes),
        )

    def trace_record(
        self,
        *,
        phase: str,
        outcome: ProtocolOutcome | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "execution_version": self.execution_version,
            "volume": VOL_131_ID,
            "phase": _token(phase, "phase", maximum=64),
            "canonical_envelope_digest": self.envelope.digest,
            "execution_digest": self.execution_digest,
            "message_id": self.envelope.message_id,
            "operation_id": self.envelope.operation_id,
            "correlation_id": self.envelope.correlation_id,
            "causation_id": self.envelope.causation_id or None,
            "trace_id": self.envelope.trace_id,
            "span_id": self.envelope.span_id or None,
            "tenant_id": self.tenant_id,
            "authority_digest": self.authority_digest,
            "attempt": self.envelope.attempt,
            "max_attempts": self.max_attempts,
            "deadline_utc": self.envelope.deadline_utc,
        }
        if outcome is not None:
            try:
                result["outcome"] = ProtocolOutcome(outcome).value
            except ValueError as exc:
                raise ProtocolExecutionError(
                    "unsupported protocol outcome"
                ) from exc
        return result


@dataclass(frozen=True, slots=True)
class ProtocolReceipt:
    """Observer evidence for one exact canonical+execution envelope pair."""

    canonical_envelope_digest: str
    execution_digest: str
    operation_id: str
    correlation_id: str
    trace_id: str
    span_id: str
    observer: str
    outcome: ProtocolOutcome
    observed_at_utc: str
    reason: str | None = None
    result_digest: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("canonical_envelope_digest", "execution_digest"):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        for field in (
            "operation_id",
            "correlation_id",
            "trace_id",
            "span_id",
            "observer",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        try:
            object.__setattr__(self, "outcome", ProtocolOutcome(self.outcome))
        except ValueError as exc:
            raise ProtocolExecutionError(
                "unsupported protocol receipt outcome"
            ) from exc
        object.__setattr__(
            self,
            "observed_at_utc",
            _timestamp(self.observed_at_utc, "observed_at_utc"),
        )
        if self.reason is not None:
            object.__setattr__(
                self,
                "reason",
                _text(self.reason, "reason", maximum=MAX_REASON_CHARS),
            )
        if self.result_digest is not None:
            object.__setattr__(
                self,
                "result_digest",
                _sha256(self.result_digest, "result_digest"),
            )
        if self.schema_version != 1:
            raise ProtocolExecutionError(
                "unsupported protocol receipt schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "canonical_envelope_digest": self.canonical_envelope_digest,
            "execution_digest": self.execution_digest,
            "operation_id": self.operation_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "observer": self.observer,
            "outcome": self.outcome.value,
            "observed_at_utc": self.observed_at_utc,
            "reason": self.reason,
            "result_digest": self.result_digest,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.payload())

    @classmethod
    def from_execution(
        cls,
        execution: ProtocolExecutionEnvelope,
        *,
        observer: str,
        outcome: ProtocolOutcome,
        observed_at_utc: str,
        reason: str | None = None,
        result_digest: str | None = None,
    ) -> "ProtocolReceipt":
        if not isinstance(execution, ProtocolExecutionEnvelope):
            raise TypeError("execution must be ProtocolExecutionEnvelope")
        observed = _timestamp(observed_at_utc, "observed_at_utc")
        if _timestamp_dt(observed) < _timestamp_dt(execution.issued_at_utc):
            raise ProtocolExecutionError(
                "receipt cannot predate execution envelope"
            )
        return cls(
            canonical_envelope_digest=execution.envelope.digest,
            execution_digest=execution.execution_digest,
            operation_id=execution.envelope.operation_id,
            correlation_id=execution.envelope.correlation_id,
            trace_id=execution.envelope.trace_id,
            span_id=execution.envelope.span_id,
            observer=observer,
            outcome=outcome,
            observed_at_utc=observed,
            reason=reason,
            result_digest=result_digest,
        )


def validate_receipt(
    execution: ProtocolExecutionEnvelope,
    receipt: ProtocolReceipt,
) -> None:
    if not isinstance(execution, ProtocolExecutionEnvelope):
        raise TypeError("execution must be ProtocolExecutionEnvelope")
    if not isinstance(receipt, ProtocolReceipt):
        raise TypeError("receipt must be ProtocolReceipt")
    if receipt.canonical_envelope_digest != execution.envelope.digest:
        raise ProtocolExecutionError(
            "receipt does not bind canonical envelope digest"
        )
    if receipt.execution_digest != execution.execution_digest:
        raise ProtocolExecutionError("receipt does not bind execution digest")
    if receipt.operation_id != execution.envelope.operation_id:
        raise ProtocolExecutionError("receipt operation identity mismatch")
    if receipt.correlation_id != execution.envelope.correlation_id:
        raise ProtocolExecutionError("receipt correlation identity mismatch")
    if receipt.trace_id != execution.envelope.trace_id:
        raise ProtocolExecutionError("receipt trace identity mismatch")
    if receipt.span_id != execution.envelope.span_id:
        raise ProtocolExecutionError("receipt span identity mismatch")
    if _timestamp_dt(receipt.observed_at_utc) < _timestamp_dt(
        execution.issued_at_utc
    ):
        raise ProtocolExecutionError("receipt predates execution envelope")


def canonical_payload_digest(payload: object) -> str:
    """Digest JSON-shaped payload data for callers that store by reference."""
    return _canonical_digest(payload)


__all__ = [
    "INTERNAL_PROTOCOL_EXECUTION_VERSION",
    "VOL_131_ID",
    "ProtocolExecutionEnvelope",
    "ProtocolExecutionError",
    "ProtocolOutcome",
    "ProtocolReceipt",
    "canonical_payload_digest",
    "validate_receipt",
]
