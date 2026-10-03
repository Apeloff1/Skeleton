"""Integrated cost governor over the canonical admission and quota runtime.

VOL-186 does not introduce another ledger.  The governor composes the existing
AdmissionRuntime, tenant quota ledger, incremental usage metering, unknown-usage
fencing, terminal reconciliation, and budget-accounting qualification.

A cheaper fallback is attempted only for declared resource-budget failures.
Concurrency, queue, deadline, shared-pressure, identity, and accounting
failures are never bypassed by fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterable

from skeleton.ai.runtime.observability.budget_accounting import (
    BudgetAccountingDecision,
    qualify_budget_accounting,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import (
    AdmissionCompletion,
    AdmissionLease,
    AdmissionRuntime,
    AdmissionRuntimeConflict,
    AdmissionRuntimeError,
    UnknownUsageMarker,
)
from skeleton.intelligence.quota import (
    QuotaCompletion,
    QuotaConflict,
    QuotaError,
    QuotaReservation,
    QuotaUsage,
    QuotaUsageEvent,
    TenantQuota,
)
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger


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


@dataclass(frozen=True, slots=True)
class SafeCostFallback:
    """Declared cheaper capability used only for bounded budget failures."""

    fallback_id: str
    capability: str
    estimate: UsageEstimate
    allowed_failure_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "fallback_id",
            _token("fallback_id", self.fallback_id),
        )
        object.__setattr__(
            self,
            "capability",
            _token("capability", self.capability),
        )
        if not isinstance(self.estimate, UsageEstimate):
            raise CostGovernorError("estimate must be UsageEstimate")
        reasons = tuple(sorted(set(self.allowed_failure_reasons)))
        if not reasons:
            raise CostGovernorError(
                "allowed_failure_reasons must be non-empty"
            )
        for reason in reasons:
            clean = _token("allowed_failure_reason", reason)
            if clean not in _SAFE_FALLBACK_REASON_PREFIXES:
                raise CostGovernorError(
                    f"unsafe fallback failure reason:{clean}"
                )
        object.__setattr__(self, "allowed_failure_reasons", reasons)

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "fallback_id": self.fallback_id,
                "capability": self.capability,
                "estimate": _usage_payload(self.estimate),
                "allowed_failure_reasons": list(
                    self.allowed_failure_reasons
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class CostReservation:
    """Receipt binding cost governance to one canonical admission lease."""

    operation_id: str
    tenant_id: str
    requested_capability: str
    selected_capability: str
    requested_request_digest: str
    selected_request_digest: str
    admission_decision_id: str
    lease_id: str
    quota_reservation_digest: str | None
    selected_estimate_digest: str
    fallback_used: bool
    fallback_id: str | None = None
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "tenant_id",
            "requested_capability",
            "selected_capability",
            "admission_decision_id",
            "lease_id",
        ):
            object.__setattr__(
                self,
                name,
                _token(name, getattr(self, name)),
            )
        for name in (
            "requested_request_digest",
            "selected_request_digest",
            "selected_estimate_digest",
        ):
            object.__setattr__(
                self,
                name,
                _sha256(name, getattr(self, name)),
            )
        if self.quota_reservation_digest is not None:
            object.__setattr__(
                self,
                "quota_reservation_digest",
                _sha256(
                    "quota_reservation_digest",
                    self.quota_reservation_digest,
                ),
            )
        if not isinstance(self.fallback_used, bool):
            raise CostGovernorError("fallback_used must be boolean")
        if self.fallback_used:
            object.__setattr__(
                self,
                "fallback_id",
                _token("fallback_id", self.fallback_id),
            )
            object.__setattr__(
                self,
                "fallback_reason",
                _token("fallback_reason", self.fallback_reason),
            )
            if self.requested_capability == self.selected_capability:
                raise CostGovernorError(
                    "fallback must select a distinct declared capability"
                )
        elif self.fallback_id is not None or self.fallback_reason is not None:
            raise CostGovernorError(
                "non-fallback reservation cannot carry fallback metadata"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "requested_capability": self.requested_capability,
            "selected_capability": self.selected_capability,
            "requested_request_digest": self.requested_request_digest,
            "selected_request_digest": self.selected_request_digest,
            "admission_decision_id": self.admission_decision_id,
            "lease_id": self.lease_id,
            "quota_reservation_digest": self.quota_reservation_digest,
            "selected_estimate_digest": self.selected_estimate_digest,
            "fallback_used": self.fallback_used,
            "fallback_id": self.fallback_id,
            "fallback_reason": self.fallback_reason,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CostCharge:
    """Idempotent durable incremental usage charge receipt."""

    operation_id: str
    event_id: str
    category: str
    usage_digest: str
    quota_event_digest: str
    resolved_unknown_usage: bool = False

    def __post_init__(self) -> None:
        for name in ("operation_id", "event_id", "category"):
            object.__setattr__(
                self,
                name,
                _token(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "usage_digest",
            _sha256("usage_digest", self.usage_digest),
        )
        object.__setattr__(
            self,
            "quota_event_digest",
            _sha256("quota_event_digest", self.quota_event_digest),
        )
        if not isinstance(self.resolved_unknown_usage, bool):
            raise CostGovernorError(
                "resolved_unknown_usage must be boolean"
            )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "operation_id": self.operation_id,
                "event_id": self.event_id,
                "category": self.category,
                "usage_digest": self.usage_digest,
                "quota_event_digest": self.quota_event_digest,
                "resolved_unknown_usage": self.resolved_unknown_usage,
            }
        )


@dataclass(frozen=True, slots=True)
class CostDecision:
    """Terminal cost-governance evidence for completion or unspent release."""

    operation_id: str
    tenant_id: str
    state: str
    reservation_digest: str
    completion_digest: str | None
    accounting_decision_digest: str | None
    accepted: bool
    reasons: tuple[str, ...]
    promotion_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _token("operation_id", self.operation_id),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _token("tenant_id", self.tenant_id),
        )
        if self.state not in {"completed", "released_unspent"}:
            raise CostGovernorError("unknown cost decision state")
        object.__setattr__(
            self,
            "reservation_digest",
            _sha256("reservation_digest", self.reservation_digest),
        )
        if self.completion_digest is not None:
            object.__setattr__(
                self,
                "completion_digest",
                _sha256("completion_digest", self.completion_digest),
            )
        if self.accounting_decision_digest is not None:
            object.__setattr__(
                self,
                "accounting_decision_digest",
                _sha256(
                    "accounting_decision_digest",
                    self.accounting_decision_digest,
                ),
            )
        if not isinstance(self.accepted, bool):
            raise CostGovernorError("accepted must be boolean")
        reasons = tuple(sorted(set(self.reasons)))
        if any(not isinstance(item, str) or not item for item in reasons):
            raise CostGovernorError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(self, "reasons", reasons)
        if self.state == "released_unspent":
            if self.completion_digest is not None:
                raise CostGovernorError(
                    "released reservation cannot carry completion"
                )
            if self.accounting_decision_digest is not None:
                raise CostGovernorError(
                    "released reservation cannot carry accounting decision"
                )
            if self.accepted:
                raise CostGovernorError(
                    "released reservation is not completed cost evidence"
                )
        else:
            if self.completion_digest is None:
                raise CostGovernorError(
                    "completed decision requires completion digest"
                )
            if self.accounting_decision_digest is None:
                raise CostGovernorError(
                    "completed decision requires accounting qualification"
                )
            if self.accepted != (not reasons):
                raise CostGovernorError(
                    "accepted state must match terminal reasons"
                )
        if self.promotion_authority is not False:
            raise CostGovernorError(
                "cost governor has no promotion authority"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "state": self.state,
            "reservation_digest": self.reservation_digest,
            "completion_digest": self.completion_digest,
            "accounting_decision_digest": self.accounting_decision_digest,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "promotion_authority": False,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


def _quota_usage_from_payload(value: object) -> QuotaUsage:
    if not isinstance(value, dict):
        raise CostGovernorError("quota usage journal payload is invalid")
    try:
        return QuotaUsage(
            operations=int(value["operations"]),
            input_tokens=int(value["input_tokens"]),
            output_tokens=int(value["output_tokens"]),
            cost_usd=float(value["cost_usd"]),
            tool_calls=int(value["tool_calls"]),
            artifact_bytes=int(value["artifact_bytes"]),
            storage_bytes=int(value["storage_bytes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "quota usage journal payload is invalid"
        ) from exc


def _quota_reservation_from_payload(value: object) -> QuotaReservation:
    if not isinstance(value, dict):
        raise CostGovernorError(
            "quota reservation journal payload is invalid"
        )
    try:
        return QuotaReservation(
            reservation_id=str(value["reservation_id"]),
            tenant_id=str(value["tenant_id"]),
            window_id=str(value["window_id"]),
            operation_id=str(value["operation_id"]),
            estimate=_quota_usage_from_payload(value["estimate"]),
            reserved_at=float(value["reserved_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "quota reservation journal payload is invalid"
        ) from exc


def _cost_reservation_from_payload(value: object) -> CostReservation:
    if not isinstance(value, dict):
        raise CostGovernorError("cost reservation journal payload is invalid")
    try:
        return CostReservation(
            operation_id=value["operation_id"],
            tenant_id=value["tenant_id"],
            requested_capability=value["requested_capability"],
            selected_capability=value["selected_capability"],
            requested_request_digest=value["requested_request_digest"],
            selected_request_digest=value["selected_request_digest"],
            admission_decision_id=value["admission_decision_id"],
            lease_id=value["lease_id"],
            quota_reservation_digest=value.get("quota_reservation_digest"),
            selected_estimate_digest=value["selected_estimate_digest"],
            fallback_used=value["fallback_used"],
            fallback_id=value.get("fallback_id"),
            fallback_reason=value.get("fallback_reason"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "cost reservation journal payload is invalid"
        ) from exc


def _cost_decision_from_payload(value: object) -> CostDecision:
    if not isinstance(value, dict):
        raise CostGovernorError("cost decision journal payload is invalid")
    try:
        return CostDecision(
            operation_id=value["operation_id"],
            tenant_id=value["tenant_id"],
            state=value["state"],
            reservation_digest=value["reservation_digest"],
            completion_digest=value.get("completion_digest"),
            accounting_decision_digest=value.get(
                "accounting_decision_digest"
            ),
            accepted=value["accepted"],
            reasons=tuple(value["reasons"]),
            promotion_authority=value.get(
                "promotion_authority",
                False,
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "cost decision journal payload is invalid"
        ) from exc


def _evidence_digest(refs: tuple[EvidenceRef, ...]) -> str:
    return _canonical_digest(
        [
            {
                "source": item.source,
                "digest": item.digest,
                "category": item.category,
            }
            for item in refs
        ]
    )


@dataclass(frozen=True, slots=True)
class _CostJournalRecord:
    operation_id: str
    tenant_id: str
    requested_request_digest: str
    reservation: CostReservation
    quota_reservation: QuotaReservation
    state: str
    terminal: CostDecision | None
    evidence_digest: str | None


class _SqliteCostGovernorJournal:
    """Durable metadata journal; spend authority stays in quota tables."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS cost_governor_journal (
        operation_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        requested_request_digest TEXT NOT NULL,
        reservation_json TEXT NOT NULL,
        quota_reservation_json TEXT NOT NULL,
        state TEXT NOT NULL,
        terminal_json TEXT,
        evidence_digest TEXT,
        CHECK (state IN ('active', 'completed', 'released_unspent'))
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with self._connect() as conn:
            conn.execute(self._SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @staticmethod
    def _decode_json(raw: object, field: str) -> dict[str, Any]:
        if not isinstance(raw, str):
            raise CostGovernorError(f"{field} journal value is invalid")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CostGovernorError(
                f"{field} journal value is invalid"
            ) from exc
        if not isinstance(value, dict):
            raise CostGovernorError(f"{field} journal value is invalid")
        return value

    @classmethod
    def _record(cls, row: sqlite3.Row) -> _CostJournalRecord:
        terminal = (
            None
            if row["terminal_json"] is None
            else _cost_decision_from_payload(
                cls._decode_json(row["terminal_json"], "terminal")
            )
        )
        return _CostJournalRecord(
            operation_id=str(row["operation_id"]),
            tenant_id=str(row["tenant_id"]),
            requested_request_digest=str(
                row["requested_request_digest"]
            ),
            reservation=_cost_reservation_from_payload(
                cls._decode_json(row["reservation_json"], "reservation")
            ),
            quota_reservation=_quota_reservation_from_payload(
                cls._decode_json(
                    row["quota_reservation_json"],
                    "quota_reservation",
                )
            ),
            state=str(row["state"]),
            terminal=terminal,
            evidence_digest=(
                None
                if row["evidence_digest"] is None
                else str(row["evidence_digest"])
            ),
        )

    def load(self, operation_id: str) -> _CostJournalRecord | None:
        operation = _token("operation_id", operation_id)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM cost_governor_journal
                WHERE operation_id = ?
                """,
                (operation,),
            ).fetchone()
        return None if row is None else self._record(row)

    def record_active(
        self,
        *,
        requested_request_digest: str,
        reservation: CostReservation,
        quota_reservation: QuotaReservation,
    ) -> _CostJournalRecord:
        requested = _sha256(
            "requested_request_digest",
            requested_request_digest,
        )
        reservation_json = _canonical_json_text(reservation.as_dict())
        quota_json = _canonical_json_text(quota_reservation.as_dict())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cost_governor_journal
                    WHERE operation_id = ?
                    """,
                    (reservation.operation_id,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO cost_governor_journal (
                            operation_id, tenant_id,
                            requested_request_digest,
                            reservation_json, quota_reservation_json,
                            state, terminal_json, evidence_digest
                        ) VALUES (?, ?, ?, ?, ?, 'active', NULL, NULL)
                        """,
                        (
                            reservation.operation_id,
                            reservation.tenant_id,
                            requested,
                            reservation_json,
                            quota_json,
                        ),
                    )
                else:
                    existing = self._record(row)
                    if existing.state != "active":
                        raise CostGovernorConflict(
                            "operation already has terminal cost journal state"
                        )
                    if (
                        existing.requested_request_digest != requested
                        or existing.reservation != reservation
                        or existing.quota_reservation != quota_reservation
                    ):
                        raise CostGovernorConflict(
                            "active cost journal replayed with different inputs"
                        )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        loaded = self.load(reservation.operation_id)
        if loaded is None:
            raise CostGovernorError("cost journal active write was lost")
        return loaded

    def record_terminal(
        self,
        decision: CostDecision,
        *,
        evidence_digest: str | None,
    ) -> _CostJournalRecord:
        evidence = (
            None
            if evidence_digest is None
            else _sha256("evidence_digest", evidence_digest)
        )
        terminal_json = _canonical_json_text(decision.as_dict())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cost_governor_journal
                    WHERE operation_id = ?
                    """,
                    (decision.operation_id,),
                ).fetchone()
                if row is None:
                    raise CostGovernorError(
                        "terminal cost journal requires active reservation"
                    )
                existing = self._record(row)
                if existing.state == "active":
                    conn.execute(
                        """
                        UPDATE cost_governor_journal
                        SET state = ?, terminal_json = ?,
                            evidence_digest = ?
                        WHERE operation_id = ?
                        """,
                        (
                            decision.state,
                            terminal_json,
                            evidence,
                            decision.operation_id,
                        ),
                    )
                elif (
                    existing.state != decision.state
                    or existing.terminal != decision
                    or existing.evidence_digest != evidence
                ):
                    raise CostGovernorConflict(
                        "terminal cost journal replayed with different inputs"
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        loaded = self.load(decision.operation_id)
        if loaded is None:
            raise CostGovernorError("cost journal terminal write was lost")
        return loaded


@dataclass(slots=True)
class _ActiveCostReservation:
    requested_request_digest: str
    receipt: CostReservation


class CostGovernor:
    """Integrated admission/quota governor with declared safe fallback."""

    def __init__(
        self,
        runtime: AdmissionRuntime,
        *,
        journal: _SqliteCostGovernorJournal | None = None,
    ) -> None:
        if not isinstance(runtime, AdmissionRuntime):
            raise TypeError("runtime must be AdmissionRuntime")
        if journal is not None and not isinstance(
            journal,
            _SqliteCostGovernorJournal,
        ):
            raise TypeError("journal must be _SqliteCostGovernorJournal")
        self.runtime = runtime
        self._journal = journal
        self._lock = threading.RLock()
        self._active: dict[str, _ActiveCostReservation] = {}

    @classmethod
    def durable(
        cls,
        path: str | Path,
        *,
        default_tenant_quota: TenantQuota,
    ) -> "CostGovernor":
        if not isinstance(default_tenant_quota, TenantQuota):
            raise TypeError(
                "default_tenant_quota must be TenantQuota"
            )
        ledger = SqliteTenantQuotaLedger(path)
        runtime = AdmissionRuntime(
            quota_ledger=ledger,
            default_tenant_quota=default_tenant_quota,
        )
        return cls(
            runtime,
            journal=_SqliteCostGovernorJournal(path),
        )

    @staticmethod
    def _receipt(
        *,
        requested: AdmissionRequest,
        selected: AdmissionRequest,
        lease: AdmissionLease,
        fallback: SafeCostFallback | None,
        fallback_reason: str | None,
    ) -> CostReservation:
        reservation = lease.quota_reservation
        return CostReservation(
            operation_id=requested.operation_id,
            tenant_id=requested.tenant_id,
            requested_capability=requested.capability,
            selected_capability=selected.capability,
            requested_request_digest=_request_digest(requested),
            selected_request_digest=_request_digest(selected),
            admission_decision_id=lease.decision.decision_id,
            lease_id=lease.lease_id,
            quota_reservation_digest=_quota_reservation_digest(reservation),
            selected_estimate_digest=_canonical_digest(
                _usage_payload(selected.estimate)
            ),
            fallback_used=fallback is not None,
            fallback_id=None if fallback is None else fallback.fallback_id,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def _fallback_request(
        requested: AdmissionRequest,
        fallback: SafeCostFallback,
    ) -> AdmissionRequest:
        if fallback.capability == requested.capability:
            raise CostGovernorError(
                "fallback must declare a distinct reduced capability"
            )
        if not _strictly_cheaper(
            requested.estimate,
            fallback.estimate,
        ):
            raise CostGovernorError(
                "fallback estimate must be component-wise no greater and strictly cheaper"
            )
        return replace(
            requested,
            capability=fallback.capability,
            estimate=fallback.estimate,
        )

    def reserve(
        self,
        request: AdmissionRequest,
        *,
        fallback: SafeCostFallback | None = None,
        now_monotonic: float | None = None,
        now_wall: float | None = None,
    ) -> CostReservation:
        if not isinstance(request, AdmissionRequest):
            raise TypeError("request must be AdmissionRequest")
        if fallback is not None and not isinstance(
            fallback,
            SafeCostFallback,
        ):
            raise TypeError("fallback must be SafeCostFallback")
        requested_digest = _request_digest(request)

        with self._lock:
            current = self._active.get(request.operation_id)
            if current is not None:
                if current.requested_request_digest != requested_digest:
                    raise CostGovernorError(
                        "operation already has a cost reservation with different requested inputs"
                    )
                return current.receipt

            try:
                lease = self.runtime.admit(
                    request,
                    now_monotonic=now_monotonic,
                    now_wall=now_wall,
                )
                receipt = self._receipt(
                    requested=request,
                    selected=request,
                    lease=lease,
                    fallback=None,
                    fallback_reason=None,
                )
            except AdmissionError as original_exc:
                reason = str(original_exc)
                if fallback is None:
                    raise CostGovernorDenied(reason) from original_exc
                if not _fallback_reason_allowed(
                    reason,
                    fallback.allowed_failure_reasons,
                ):
                    raise CostGovernorDenied(reason) from original_exc
                selected = self._fallback_request(
                    request,
                    fallback,
                )
                try:
                    lease = self.runtime.admit(
                        selected,
                        now_monotonic=now_monotonic,
                        now_wall=now_wall,
                    )
                except AdmissionError as fallback_exc:
                    raise CostGovernorDenied(
                        f"declared_cost_fallback_denied:{fallback_exc}"
                    ) from fallback_exc
                except AdmissionRuntimeConflict as fallback_exc:
                    raise CostGovernorConflict(
                        f"declared_cost_fallback_conflict:{fallback_exc}"
                    ) from fallback_exc
                except AdmissionRuntimeError as fallback_exc:
                    raise CostGovernorError(
                        f"declared_cost_fallback_runtime_error:{fallback_exc}"
                    ) from fallback_exc
                receipt = self._receipt(
                    requested=request,
                    selected=selected,
                    lease=lease,
                    fallback=fallback,
                    fallback_reason=reason,
                )
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc

            if self._journal is not None:
                quota_reservation = lease.quota_reservation
                if quota_reservation is None:
                    try:
                        self.runtime.release(lease.operation_id)
                    except Exception:
                        pass
                    raise CostGovernorError(
                        "durable cost governor requires quota reservation"
                    )
                try:
                    self._journal.record_active(
                        requested_request_digest=requested_digest,
                        reservation=receipt,
                        quota_reservation=quota_reservation,
                    )
                except Exception:
                    try:
                        self.runtime.release(lease.operation_id)
                    except Exception:
                        pass
                    raise

            self._active[request.operation_id] = _ActiveCostReservation(
                requested_request_digest=requested_digest,
                receipt=receipt,
            )
            return receipt

    def charge(
        self,
        operation_id: str,
        event_id: str,
        category: str,
        delta: UsageEstimate,
        *,
        now_wall: float | None = None,
    ) -> CostCharge:
        operation = _token("operation_id", operation_id)
        event = _token("event_id", event_id)
        clean_category = _token("category", category)
        if not isinstance(delta, UsageEstimate):
            raise TypeError("delta must be UsageEstimate")
        with self._lock:
            if operation not in self._active:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                recorded = self.runtime.record_usage_event(
                    operation,
                    event,
                    clean_category,
                    delta,
                    now_wall=now_wall,
                )
            except AdmissionError as exc:
                raise CostGovernorDenied(str(exc)) from exc
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc
        return CostCharge(
            operation_id=operation,
            event_id=event,
            category=recorded.category,
            usage_digest=_canonical_digest(
                _usage_payload(delta)
            ),
            quota_event_digest=_usage_event_digest(recorded),
        )

    def mark_usage_unknown(
        self,
        operation_id: str,
        event_id: str,
        category: str,
        reason: str,
        *,
        now_wall: float | None = None,
    ) -> UnknownUsageMarker:
        operation = _token("operation_id", operation_id)
        with self._lock:
            if operation not in self._active:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                return self.runtime.mark_usage_unknown(
                    operation,
                    event_id,
                    category,
                    reason,
                    now_wall=now_wall,
                )
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc

    def resolve_unknown_usage(
        self,
        operation_id: str,
        event_id: str,
        delta: UsageEstimate,
        *,
        now_wall: float | None = None,
    ) -> CostCharge:
        operation = _token("operation_id", operation_id)
        event = _token("event_id", event_id)
        if not isinstance(delta, UsageEstimate):
            raise TypeError("delta must be UsageEstimate")
        with self._lock:
            if operation not in self._active:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                recorded = self.runtime.resolve_unknown_usage(
                    operation,
                    event,
                    delta,
                    now_wall=now_wall,
                )
            except AdmissionError as exc:
                raise CostGovernorDenied(str(exc)) from exc
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc
        return CostCharge(
            operation_id=operation,
            event_id=event,
            category=recorded.category,
            usage_digest=_canonical_digest(
                _usage_payload(delta)
            ),
            quota_event_digest=_usage_event_digest(recorded),
            resolved_unknown_usage=True,
        )

    def _completed_decision(
        self,
        *,
        operation_id: str,
        receipt: CostReservation,
        quota_reservation: QuotaReservation,
        quota_completion: QuotaCompletion,
        refs: tuple[EvidenceRef, ...],
    ) -> CostDecision:
        ledger = self.runtime.quota_ledger
        if ledger is None:
            raise CostGovernorError(
                "cost completion requires quota ledger"
            )
        if quota_reservation.operation_id != operation_id:
            raise CostGovernorConflict(
                "cost journal reservation operation mismatch"
            )
        if quota_completion.operation_id != operation_id:
            raise CostGovernorConflict(
                "cost completion operation mismatch"
            )
        if quota_completion.reservation_id != quota_reservation.reservation_id:
            raise CostGovernorConflict(
                "cost completion reservation mismatch"
            )
        snapshot = ledger.snapshot(quota_completion.tenant_id)
        accounting: BudgetAccountingDecision = qualify_budget_accounting(
            tenant_id=quota_completion.tenant_id,
            operation_id=operation_id,
            reservation=quota_reservation,
            completion=quota_completion,
            snapshot=snapshot,
            evidence_refs=refs,
        )
        reasons = list(accounting.reasons)
        if quota_completion.overrun:
            reasons.append(
                "cost-overrun:"
                + ",".join(quota_completion.overrun_dimensions)
            )
        normalized = tuple(sorted(set(reasons)))
        return CostDecision(
            operation_id=operation_id,
            tenant_id=quota_completion.tenant_id,
            state="completed",
            reservation_digest=receipt.digest,
            completion_digest=_completion_digest(quota_completion),
            accounting_decision_digest=accounting.decision_digest,
            accepted=not normalized,
            reasons=normalized,
        )

    def recover_completed(
        self,
        operation_id: str,
        *,
        evidence_refs: Iterable[EvidenceRef],
    ) -> CostDecision:
        """Recover terminal qualification after a post-completion process loss."""

        operation = _token("operation_id", operation_id)
        refs = _validated_evidence_refs(evidence_refs)
        evidence = _evidence_digest(refs)
        journal = self._journal
        if journal is None:
            raise CostGovernorError(
                "completed recovery requires durable cost journal"
            )

        with self._lock:
            record = journal.load(operation)
            if record is None:
                raise CostGovernorError(
                    "operation has no durable cost journal record"
                )
            if record.state == "released_unspent":
                raise CostGovernorConflict(
                    "released reservation cannot be recovered as completed"
                )
            if record.terminal is not None:
                if record.state != "completed":
                    raise CostGovernorConflict(
                        "terminal cost journal state is inconsistent"
                    )
                if record.evidence_digest != evidence:
                    raise CostGovernorConflict(
                        "completed recovery replayed with different evidence"
                    )
                self._active.pop(operation, None)
                return record.terminal

            ledger = self.runtime.quota_ledger
            if ledger is None:
                raise CostGovernorError(
                    "completed recovery requires quota ledger"
                )
            finder = getattr(ledger, "completion_for_operation", None)
            if not callable(finder):
                raise CostGovernorError(
                    "quota ledger does not support completion recovery"
                )
            try:
                completion = finder(record.tenant_id, operation)
            except QuotaError as exc:
                raise CostGovernorError(
                    "durable completion lookup failed"
                ) from exc
            if completion is None:
                raise CostGovernorError(
                    "operation has no durable completed accounting"
                )

            decision = self._completed_decision(
                operation_id=operation,
                receipt=record.reservation,
                quota_reservation=record.quota_reservation,
                quota_completion=completion,
                refs=refs,
            )
            journal.record_terminal(
                decision,
                evidence_digest=evidence,
            )
            if self._journal is not None:
                self._journal.record_terminal(
                    decision,
                    evidence_digest=None,
                )
            self._active.pop(operation, None)
            return decision

    def complete(
        self,
        operation_id: str,
        actual: UsageEstimate,
        *,
        evidence_refs: Iterable[EvidenceRef],
        now_wall: float | None = None,
    ) -> CostDecision:
        operation = _token("operation_id", operation_id)
        if not isinstance(actual, UsageEstimate):
            raise TypeError("actual must be UsageEstimate")
        refs = _validated_evidence_refs(evidence_refs)
        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                completion: AdmissionCompletion = self.runtime.complete(
                    operation,
                    actual,
                    now_wall=now_wall,
                )
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc

            # The runtime lease is terminal after complete(). From this point on
            # recovery must use the durable journal + quota completion.
            self._active.pop(operation, None)
            try:
                quota_completion = completion.quota_completion
                quota_reservation = completion.lease.quota_reservation
                if quota_completion is None or quota_reservation is None:
                    raise CostGovernorError(
                        "cost completion requires durable quota accounting"
                    )
                decision = self._completed_decision(
                    operation_id=operation,
                    receipt=active.receipt,
                    quota_reservation=quota_reservation,
                    quota_completion=quota_completion,
                    refs=refs,
                )
                if self._journal is not None:
                    self._journal.record_terminal(
                        decision,
                        evidence_digest=_evidence_digest(refs),
                    )
                return decision
            except CostGovernorError:
                raise
            except Exception as exc:
                raise CostGovernorError(
                    "terminal_accounting_qualification_failed"
                ) from exc

    def release_unspent(
        self,
        operation_id: str,
    ) -> CostDecision:
        operation = _token("operation_id", operation_id)
        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                lease = self.runtime.release(operation)
            except (AdmissionRuntimeConflict, QuotaConflict) as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except (AdmissionRuntimeError, QuotaError) as exc:
                raise CostGovernorError(str(exc)) from exc
            decision = CostDecision(
                operation_id=operation,
                tenant_id=lease.tenant_id,
                state="released_unspent",
                reservation_digest=active.receipt.digest,
                completion_digest=None,
                accounting_decision_digest=None,
                accepted=False,
                reasons=("reservation-released-unspent",),
            )
            self._active.pop(operation, None)
            return decision

    def active_reservations(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._active))


__all__ = [
    "CostCharge",
    "CostDecision",
    "CostGovernor",
    "CostGovernorConflict",
    "CostGovernorDenied",
    "CostGovernorError",
    "CostReservation",
    "SafeCostFallback",
]
