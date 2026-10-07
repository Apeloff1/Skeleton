"""Canonical internal protocol envelopes with trace and retry semantics.

VOL-131 Internal Protocols requires stable envelopes carrying correlation,
causation, deadline, retry/idempotency, and trace identity.  This module is
transport-neutral: it does not open sockets, persist messages, or execute
effects.  It provides the deterministic contract that transports and workers
must preserve.

The core invariants are fail-closed:
- every envelope has one stable operation and correlation identity;
- child messages bind the parent through causation and trace parentage;
- retries cannot extend the original deadline or mutate payload/authority;
- retryable delivery requires an idempotency key and bounded attempts;
- retry attempts form a digest-bound predecessor chain;
- unknown outcomes carry an explicit recovery policy;
- trace records expose identity and digests, never raw payload content.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping


INTERNAL_PROTOCOL_SCHEMA_VERSION = 1
VOL_131_ID = "VOL-131"
MAX_ATTRIBUTES = 32
MAX_ATTRIBUTE_KEY_CHARS = 64
MAX_ATTRIBUTE_VALUE_CHARS = 256
MAX_REASON_CHARS = 1024
MAX_TOKEN_CHARS = 192

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


class ProtocolError(ValueError):
    """Internal protocol data is malformed, ambiguous, or unsafe."""


class DeliverySemantics(str, Enum):
    """Supported delivery contracts.

    AT_MOST_ONCE forbids protocol-level retry.  IDEMPOTENT_RETRY permits
    bounded retry only when one stable idempotency key is supplied.
    """

    AT_MOST_ONCE = "at_most_once"
    IDEMPOTENT_RETRY = "idempotent_retry"


class UnknownOutcomePolicy(str, Enum):
    """Required handling when execution outcome cannot be proven."""

    FAIL_CLOSED = "fail_closed"
    QUERY_STATUS = "query_status"
    RECONCILE = "reconcile"
    COMPENSATE = "compensate"


class ProtocolOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


def _text(value: object, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"{field} must be a non-empty string")
    if value != value.strip() or len(value) > maximum:
        raise ProtocolError(f"{field} must be normalized and bounded")
    return value


def _token(value: object, field: str, *, maximum: int = MAX_TOKEN_CHARS) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise ProtocolError(f"{field} must be a canonical token")
    return text


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ProtocolError(f"{field} must be lowercase sha256")
    return value


def _trace_id(value: object, field: str = "trace_id") -> str:
    if not isinstance(value, str) or not _TRACE_ID_RE.fullmatch(value):
        raise ProtocolError(f"{field} must be 32 lowercase hex characters")
    return value


def _span_id(value: object, field: str = "span_id") -> str:
    if not isinstance(value, str) or not _SPAN_ID_RE.fullmatch(value):
        raise ProtocolError(f"{field} must be 16 lowercase hex characters")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ProtocolError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProtocolError(f"{field} must be a non-negative integer")
    return value


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ProtocolError(f"{field} must be finite numeric")
    return result


def _pairs(
    values: Mapping[str, str] | Iterable[tuple[str, str]],
    *,
    field: str,
    maximum_items: int = MAX_ATTRIBUTES,
) -> tuple[tuple[str, str], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    normalized: dict[str, str] = {}
    for key, value in items:
        normalized[
            _token(key, f"{field}.key", maximum=MAX_ATTRIBUTE_KEY_CHARS)
        ] = _text(
            value,
            f"{field}.value",
            maximum=MAX_ATTRIBUTE_VALUE_CHARS,
        )
    if len(normalized) > maximum_items:
        raise ProtocolError(f"{field} exceeds item limit")
    return tuple(sorted(normalized.items()))


def canonical_json_bytes(value: object) -> bytes:
    """Serialize protocol identity data using deterministic finite JSON."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("protocol identity must be canonical JSON") from exc


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Transport-neutral trace identity propagated with each message."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    sampled: bool = True
    baggage: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _trace_id(self.trace_id))
        object.__setattr__(self, "span_id", _span_id(self.span_id))
        if self.parent_span_id is not None:
            object.__setattr__(
                self,
                "parent_span_id",
                _span_id(self.parent_span_id, "parent_span_id"),
            )
            if self.parent_span_id == self.span_id:
                raise ProtocolError("trace span cannot parent itself")
        if not isinstance(self.sampled, bool):
            raise ProtocolError("sampled must be boolean")
        object.__setattr__(
            self,
            "baggage",
            _pairs(self.baggage, field="baggage"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "sampled": self.sampled,
            "baggage": [list(item) for item in self.baggage],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def child(self, span_id: str) -> "TraceContext":
        return TraceContext(
            trace_id=self.trace_id,
            span_id=span_id,
            parent_span_id=self.span_id,
            sampled=self.sampled,
            baggage=self.baggage,
        )


@dataclass(frozen=True, slots=True)
class ProtocolEnvelope:
    """Canonical message identity for cross-boundary internal operations."""

    message_id: str
    operation_id: str
    correlation_id: str
    tenant_id: str
    sender: str
    recipient: str
    message_type: str
    payload_digest: str
    authority_digest: str
    trace: TraceContext
    issued_at_ms: int
    deadline_at_ms: int
    delivery_semantics: DeliverySemantics = DeliverySemantics.AT_MOST_ONCE
    unknown_outcome_policy: UnknownOutcomePolicy = UnknownOutcomePolicy.FAIL_CLOSED
    attempt: int = 1
    max_attempts: int = 1
    idempotency_key: str | None = None
    causation_id: str | None = None
    previous_envelope_digest: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    schema_version: int = INTERNAL_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "message_id",
            "operation_id",
            "correlation_id",
            "tenant_id",
            "sender",
            "recipient",
            "message_type",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "payload_digest",
            _sha256(self.payload_digest, "payload_digest"),
        )
        object.__setattr__(
            self,
            "authority_digest",
            _sha256(self.authority_digest, "authority_digest"),
        )
        if not isinstance(self.trace, TraceContext):
            raise ProtocolError("trace must be TraceContext")

        issued = _nonnegative_int(self.issued_at_ms, "issued_at_ms")
        deadline = _positive_int(self.deadline_at_ms, "deadline_at_ms")
        if deadline <= issued:
            raise ProtocolError("deadline_at_ms must exceed issued_at_ms")
        object.__setattr__(self, "issued_at_ms", issued)
        object.__setattr__(self, "deadline_at_ms", deadline)

        try:
            semantics = DeliverySemantics(self.delivery_semantics)
        except ValueError as exc:
            raise ProtocolError("unsupported delivery_semantics") from exc
        object.__setattr__(self, "delivery_semantics", semantics)
        try:
            outcome_policy = UnknownOutcomePolicy(self.unknown_outcome_policy)
        except ValueError as exc:
            raise ProtocolError("unsupported unknown_outcome_policy") from exc
        object.__setattr__(self, "unknown_outcome_policy", outcome_policy)

        attempt = _positive_int(self.attempt, "attempt")
        max_attempts = _positive_int(self.max_attempts, "max_attempts")
        if attempt > max_attempts:
            raise ProtocolError("attempt cannot exceed max_attempts")
        object.__setattr__(self, "attempt", attempt)
        object.__setattr__(self, "max_attempts", max_attempts)

        if self.idempotency_key is not None:
            object.__setattr__(
                self,
                "idempotency_key",
                _token(self.idempotency_key, "idempotency_key"),
            )
        if self.causation_id is not None:
            object.__setattr__(
                self,
                "causation_id",
                _token(self.causation_id, "causation_id"),
            )
            if self.causation_id == self.message_id:
                raise ProtocolError("message cannot cause itself")
        if self.previous_envelope_digest is not None:
            object.__setattr__(
                self,
                "previous_envelope_digest",
                _sha256(
                    self.previous_envelope_digest,
                    "previous_envelope_digest",
                ),
            )
        object.__setattr__(
            self,
            "attributes",
            _pairs(self.attributes, field="attributes"),
        )

        if semantics is DeliverySemantics.AT_MOST_ONCE:
            if max_attempts != 1 or attempt != 1:
                raise ProtocolError(
                    "at_most_once delivery forbids protocol-level retries"
                )
            if self.previous_envelope_digest is not None:
                raise ProtocolError(
                    "at_most_once envelope cannot bind retry predecessor"
                )
        else:
            if self.idempotency_key is None:
                raise ProtocolError(
                    "idempotent_retry requires idempotency_key"
                )
            if max_attempts < 2:
                raise ProtocolError(
                    "idempotent_retry requires max_attempts >= 2"
                )

        if attempt == 1 and self.previous_envelope_digest is not None:
            raise ProtocolError("first attempt cannot bind retry predecessor")
        if attempt > 1:
            if self.previous_envelope_digest is None:
                raise ProtocolError(
                    "retry attempt must bind previous_envelope_digest"
                )
            if self.causation_id is None:
                raise ProtocolError("retry attempt must bind causation_id")

        if self.schema_version != INTERNAL_PROTOCOL_SCHEMA_VERSION:
            raise ProtocolError("unsupported internal protocol schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "volume": VOL_131_ID,
            "message_id": self.message_id,
            "operation_id": self.operation_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "tenant_id": self.tenant_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "payload_digest": self.payload_digest,
            "authority_digest": self.authority_digest,
            "trace": self.trace.payload(),
            "issued_at_ms": self.issued_at_ms,
            "deadline_at_ms": self.deadline_at_ms,
            "delivery_semantics": self.delivery_semantics.value,
            "unknown_outcome_policy": self.unknown_outcome_policy.value,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "idempotency_key": self.idempotency_key,
            "previous_envelope_digest": self.previous_envelope_digest,
            "attributes": [list(item) for item in self.attributes],
        }

    @property
    def envelope_digest(self) -> str:
        return canonical_digest(self.payload())

    def remaining_ms(self, now_ms: int) -> int:
        now = _nonnegative_int(now_ms, "now_ms")
        return max(0, self.deadline_at_ms - now)

    def expired(self, now_ms: int) -> bool:
        return self.remaining_ms(now_ms) == 0

    @property
    def unknown_outcome_action(self) -> str:
        return self.unknown_outcome_policy.value

    def trace_record(
        self,
        *,
        phase: str,
        outcome: ProtocolOutcome | None = None,
    ) -> dict[str, Any]:
        """Return a bounded trace record with no raw message payload."""
        phase_token = _token(phase, "phase", maximum=64)
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "volume": VOL_131_ID,
            "phase": phase_token,
            "message_id": self.message_id,
            "operation_id": self.operation_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "tenant_id": self.tenant_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "payload_digest": self.payload_digest,
            "authority_digest": self.authority_digest,
            "envelope_digest": self.envelope_digest,
            "trace_id": self.trace.trace_id,
            "span_id": self.trace.span_id,
            "parent_span_id": self.trace.parent_span_id,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "deadline_at_ms": self.deadline_at_ms,
        }
        if outcome is not None:
            try:
                result["outcome"] = ProtocolOutcome(outcome).value
            except ValueError as exc:
                raise ProtocolError("unsupported protocol outcome") from exc
        return result

    def retry(
        self,
        *,
        message_id: str,
        span_id: str,
        now_ms: int,
    ) -> "ProtocolEnvelope":
        """Create the next bounded retry without widening authority/deadline."""
        now = _nonnegative_int(now_ms, "now_ms")
        if self.delivery_semantics is not DeliverySemantics.IDEMPOTENT_RETRY:
            raise ProtocolError("envelope is not retryable")
        if now >= self.deadline_at_ms:
            raise ProtocolError("cannot retry expired envelope")
        if self.attempt >= self.max_attempts:
            raise ProtocolError("retry attempt budget exhausted")
        return ProtocolEnvelope(
            message_id=message_id,
            operation_id=self.operation_id,
            correlation_id=self.correlation_id,
            causation_id=self.message_id,
            tenant_id=self.tenant_id,
            sender=self.sender,
            recipient=self.recipient,
            message_type=self.message_type,
            payload_digest=self.payload_digest,
            authority_digest=self.authority_digest,
            trace=self.trace.child(span_id),
            issued_at_ms=now,
            deadline_at_ms=self.deadline_at_ms,
            delivery_semantics=self.delivery_semantics,
            unknown_outcome_policy=self.unknown_outcome_policy,
            attempt=self.attempt + 1,
            max_attempts=self.max_attempts,
            idempotency_key=self.idempotency_key,
            previous_envelope_digest=self.envelope_digest,
            attributes=self.attributes,
        )

    def spawn_child(
        self,
        *,
        message_id: str,
        span_id: str,
        recipient: str,
        message_type: str,
        payload_digest: str,
        now_ms: int,
        authority_digest: str | None = None,
        delivery_semantics: DeliverySemantics = DeliverySemantics.AT_MOST_ONCE,
        unknown_outcome_policy: UnknownOutcomePolicy = UnknownOutcomePolicy.FAIL_CLOSED,
        idempotency_key: str | None = None,
        max_attempts: int = 1,
        attributes: Mapping[str, str] | Iterable[tuple[str, str]] = (),
    ) -> "ProtocolEnvelope":
        """Create a causally linked child inside the parent's deadline."""
        now = _nonnegative_int(now_ms, "now_ms")
        if now >= self.deadline_at_ms:
            raise ProtocolError("cannot spawn child after parent deadline")
        return ProtocolEnvelope(
            message_id=message_id,
            operation_id=self.operation_id,
            correlation_id=self.correlation_id,
            causation_id=self.message_id,
            tenant_id=self.tenant_id,
            sender=self.recipient,
            recipient=recipient,
            message_type=message_type,
            payload_digest=payload_digest,
            authority_digest=(
                self.authority_digest
                if authority_digest is None
                else authority_digest
            ),
            trace=self.trace.child(span_id),
            issued_at_ms=now,
            deadline_at_ms=self.deadline_at_ms,
            delivery_semantics=delivery_semantics,
            unknown_outcome_policy=unknown_outcome_policy,
            attempt=1,
            max_attempts=max_attempts,
            idempotency_key=idempotency_key,
            attributes=_pairs(attributes, field="attributes"),
        )


@dataclass(frozen=True, slots=True)
class ProtocolReceipt:
    """Observer evidence for one exact protocol envelope."""

    envelope_digest: str
    operation_id: str
    correlation_id: str
    trace_id: str
    span_id: str
    observer: str
    outcome: ProtocolOutcome
    observed_at_ms: int
    reason: str | None = None
    result_digest: str | None = None
    schema_version: int = INTERNAL_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "envelope_digest",
            _sha256(self.envelope_digest, "envelope_digest"),
        )
        object.__setattr__(
            self,
            "operation_id",
            _token(self.operation_id, "operation_id"),
        )
        object.__setattr__(
            self,
            "correlation_id",
            _token(self.correlation_id, "correlation_id"),
        )
        object.__setattr__(self, "trace_id", _trace_id(self.trace_id))
        object.__setattr__(self, "span_id", _span_id(self.span_id))
        object.__setattr__(
            self,
            "observer",
            _token(self.observer, "observer"),
        )
        try:
            object.__setattr__(self, "outcome", ProtocolOutcome(self.outcome))
        except ValueError as exc:
            raise ProtocolError("unsupported receipt outcome") from exc
        object.__setattr__(
            self,
            "observed_at_ms",
            _nonnegative_int(self.observed_at_ms, "observed_at_ms"),
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
        if self.schema_version != INTERNAL_PROTOCOL_SCHEMA_VERSION:
            raise ProtocolError("unsupported receipt schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "volume": VOL_131_ID,
            "envelope_digest": self.envelope_digest,
            "operation_id": self.operation_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "observer": self.observer,
            "outcome": self.outcome.value,
            "observed_at_ms": self.observed_at_ms,
            "reason": self.reason,
            "result_digest": self.result_digest,
        }

    @property
    def receipt_digest(self) -> str:
        return canonical_digest(self.payload())

    @classmethod
    def from_envelope(
        cls,
        envelope: ProtocolEnvelope,
        *,
        observer: str,
        outcome: ProtocolOutcome,
        observed_at_ms: int,
        reason: str | None = None,
        result_digest: str | None = None,
    ) -> "ProtocolReceipt":
        if not isinstance(envelope, ProtocolEnvelope):
            raise TypeError("envelope must be ProtocolEnvelope")
        observed = _nonnegative_int(observed_at_ms, "observed_at_ms")
        if observed < envelope.issued_at_ms:
            raise ProtocolError("receipt cannot predate envelope")
        return cls(
            envelope_digest=envelope.envelope_digest,
            operation_id=envelope.operation_id,
            correlation_id=envelope.correlation_id,
            trace_id=envelope.trace.trace_id,
            span_id=envelope.trace.span_id,
            observer=observer,
            outcome=outcome,
            observed_at_ms=observed,
            reason=reason,
            result_digest=result_digest,
        )


def validate_receipt(
    envelope: ProtocolEnvelope,
    receipt: ProtocolReceipt,
) -> None:
    """Fail closed unless receipt binds the exact envelope and trace identity."""
    if not isinstance(envelope, ProtocolEnvelope):
        raise TypeError("envelope must be ProtocolEnvelope")
    if not isinstance(receipt, ProtocolReceipt):
        raise TypeError("receipt must be ProtocolReceipt")
    if receipt.envelope_digest != envelope.envelope_digest:
        raise ProtocolError("receipt does not bind envelope digest")
    if receipt.operation_id != envelope.operation_id:
        raise ProtocolError("receipt operation identity mismatch")
    if receipt.correlation_id != envelope.correlation_id:
        raise ProtocolError("receipt correlation identity mismatch")
    if receipt.trace_id != envelope.trace.trace_id:
        raise ProtocolError("receipt trace identity mismatch")
    if receipt.span_id != envelope.trace.span_id:
        raise ProtocolError("receipt span identity mismatch")
    if receipt.observed_at_ms < envelope.issued_at_ms:
        raise ProtocolError("receipt predates envelope")


def canonical_payload_digest(payload: object) -> str:
    """Digest a JSON-compatible message body without placing it in tracing."""
    return canonical_digest(payload)


__all__ = [
    "INTERNAL_PROTOCOL_SCHEMA_VERSION",
    "VOL_131_ID",
    "DeliverySemantics",
    "ProtocolEnvelope",
    "ProtocolError",
    "ProtocolOutcome",
    "ProtocolReceipt",
    "TraceContext",
    "UnknownOutcomePolicy",
    "canonical_digest",
    "canonical_json_bytes",
    "canonical_payload_digest",
    "validate_receipt",
]
