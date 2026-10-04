"""Evidence-bound reconciliation for in-doubt non-idempotent tool effects.

A durable tool reservation can survive a process crash even when the external
side effect happened and the terminal receipt did not. Blind retry can duplicate
an external mutation. Permanent denial, on the other hand, strands work that an
independent observer can safely classify.

This module closes that ambiguity without weakening the canonical tool runtime.
It extends :class:`SQLiteToolReceiptStore` with one narrow authority: terminally
resolve an existing `pending` reservation from independent evidence. It never
calls the tool handler and never stores raw tool arguments or result payloads.

Recovery laws
-------------
* reconciliation is permitted only for an exact pending request identity;
* one pending identity accepts exactly one evidence digest;
* committed effects become synthetic SUCCEEDED receipts;
* absent or already-compensated effects become synthetic FAILED receipts;
* the original idempotency key is terminal after reconciliation;
* replaying identical evidence is stable;
* conflicting evidence, a changed request, or an already-committed normal
  receipt fails closed;
* saga orchestration must not compensate an effect proved absent or already
  compensated (handled by `tool_saga` recovery codes).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from skeleton.skills.tool_contract import (
    ToolExecutionRequest,
    ToolExecutionReceipt,
    ToolExecutionStatus,
)
from skeleton.skills.tool_receipt_store import (
    SQLiteToolReceiptStore,
    ToolReceiptConflict,
    ToolReceiptStoreError,
)


_RECONCILIATION_SCHEMA = "skeleton.tool_effect_reconciliation.v1"
_DECISIONS = frozenset(
    {"effect_committed", "effect_absent", "effect_compensated"}
)


class ToolEffectReconciliationError(ToolReceiptStoreError):
    """An in-doubt effect cannot be reconciled safely."""


class ToolEffectReconciliationConflict(ToolEffectReconciliationError):
    """A prior reconciliation conflicts with the supplied evidence."""


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ToolEffectReconciliationError(
            f"{field} must be normalized non-empty text"
        )
    if len(value) > maximum:
        raise ToolEffectReconciliationError(f"{field} exceeds maximum length")
    return value


def _utc(value: datetime, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ToolEffectReconciliationError(
            f"{field} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ToolEffectReconciliationError(f"{field} must be ISO text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ToolEffectReconciliationError(f"{field} is invalid") from exc
    return _utc(parsed, field)


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ToolEffectReconciliationError(
            "evidence_refs must be an iterable of references"
        )
    normalized: list[str] = []
    for raw in values:
        ref = _text(raw, "evidence_ref")
        if ref not in normalized:
            normalized.append(ref)
    if not normalized:
        raise ToolEffectReconciliationError(
            "reconciliation requires evidence references"
        )
    if len(normalized) > 128:
        raise ToolEffectReconciliationError(
            "reconciliation evidence exceeds maximum reference count"
        )
    return tuple(normalized)


def _canonical_digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ToolEffectReconciliationError(
            "reconciliation evidence must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _request_projection(request: ToolExecutionRequest) -> dict[str, object]:
    return {
        "request_id": request.request_id,
        "operation_id": request.operation_id,
        "execution_id": request.execution_id,
        "turn_id": request.turn_id,
        "call_id": request.call_id,
        "tenant_id": request.tenant_id,
        "tool_id": request.tool_id,
        "idempotency_key": request.idempotency_key,
        "arguments_digest": request.arguments_digest,
        "approval_ref": request.approval_ref,
        "delegated_authority_ref": request.delegated_authority_ref,
        "data_class": request.data_class,
        "transfer_purpose": request.transfer_purpose,
    }


@dataclass(frozen=True, slots=True)
class ToolEffectReconciliationEvidence:
    """Independent observation that resolves one reserved side effect."""

    decision: str
    observer_id: str
    authority_ref: str
    evidence_refs: tuple[str, ...]
    observed_at: datetime
    result_ref: str | None = None
    compensation_ref: str | None = None
    note: str | None = None
    schema_version: str = _RECONCILIATION_SCHEMA

    def __post_init__(self) -> None:
        decision = _text(self.decision, "decision", maximum=64)
        if decision not in _DECISIONS:
            raise ToolEffectReconciliationError(
                "unsupported reconciliation decision"
            )
        object.__setattr__(self, "decision", decision)
        object.__setattr__(
            self,
            "observer_id",
            _text(self.observer_id, "observer_id", maximum=256),
        )
        object.__setattr__(
            self,
            "authority_ref",
            _text(self.authority_ref, "authority_ref", maximum=512),
        )
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs))
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        if self.result_ref is not None:
            object.__setattr__(
                self,
                "result_ref",
                _text(self.result_ref, "result_ref"),
            )
        if self.compensation_ref is not None:
            object.__setattr__(
                self,
                "compensation_ref",
                _text(self.compensation_ref, "compensation_ref"),
            )
        if self.note is not None:
            object.__setattr__(
                self,
                "note",
                _text(self.note, "note"),
            )
        if self.schema_version != _RECONCILIATION_SCHEMA:
            raise ToolEffectReconciliationError(
                "unsupported reconciliation schema"
            )

        if decision == "effect_committed":
            if self.result_ref is None:
                raise ToolEffectReconciliationError(
                    "effect_committed requires result_ref"
                )
            if self.compensation_ref is not None:
                raise ToolEffectReconciliationError(
                    "effect_committed cannot carry compensation_ref"
                )
        elif decision == "effect_absent":
            if self.result_ref is not None or self.compensation_ref is not None:
                raise ToolEffectReconciliationError(
                    "effect_absent cannot carry result or compensation refs"
                )
        else:
            if self.compensation_ref is None:
                raise ToolEffectReconciliationError(
                    "effect_compensated requires compensation_ref"
                )
            if self.result_ref is not None:
                raise ToolEffectReconciliationError(
                    "effect_compensated cannot carry result_ref"
                )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "decision": self.decision,
            "observer_id": self.observer_id,
            "authority_ref": self.authority_ref,
            "evidence_refs": list(self.evidence_refs),
            "observed_at": self.observed_at.isoformat(),
            "result_ref": self.result_ref,
            "compensation_ref": self.compensation_ref,
            "note": self.note,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ToolEffectReconciliationReceipt:
    """Audit receipt binding an evidence decision to the exact tool request."""

    request_digest: str
    evidence_digest: str
    terminal_receipt_id: str
    reconciled_at: datetime

    def __post_init__(self) -> None:
        for name in ("request_digest", "evidence_digest"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ToolEffectReconciliationError(
                    f"{name} must be lowercase sha256"
                )
        _text(self.terminal_receipt_id, "terminal_receipt_id", maximum=64)
        object.__setattr__(
            self,
            "reconciled_at",
            _utc(self.reconciled_at, "reconciled_at"),
        )


def _terminal_receipt_id(
    request: ToolExecutionRequest,
    evidence: ToolEffectReconciliationEvidence,
) -> str:
    digest = _canonical_digest(
        {
            "schema": "skeleton.tool_effect_reconciliation.receipt_id.v1",
            "request": _request_projection(request),
            "evidence_digest": evidence.digest,
        }
    )
    return (
        f"{digest[0:8]}-{digest[8:12]}-4{digest[13:16]}-"
        f"8{digest[17:20]}-{digest[20:32]}"
    )


class ReconciliableToolReceiptStore(SQLiteToolReceiptStore):
    """SQLite receipt store with terminal in-doubt reconciliation authority."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "tool_execution",
    ) -> None:
        super().__init__(path, namespace=namespace)
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tool_effect_reconciliation (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    terminal_receipt_id TEXT NOT NULL,
                    reconciled_at TEXT NOT NULL,
                    PRIMARY KEY(
                        namespace,
                        tenant_id,
                        operation_id,
                        idempotency_key
                    )
                );
                """
            )

    def _row(
        self,
        request: ToolExecutionRequest,
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM tool_execution_receipt
            WHERE namespace = ?
              AND tenant_id = ?
              AND operation_id = ?
              AND idempotency_key = ?
            """,
            (
                self.namespace,
                request.tenant_id,
                request.operation_id,
                request.idempotency_key,
            ),
        ).fetchone()

    @staticmethod
    def _assert_exact_identity(
        row: sqlite3.Row,
        request: ToolExecutionRequest,
    ) -> None:
        if (
            row["request_id"] != request.request_id
            or row["tool_id"] != request.tool_id
            or row["arguments_digest"] != request.arguments_digest
            or row["execution_id"] != request.execution_id
            or row["turn_id"] != request.turn_id
            or row["call_id"] != request.call_id
            or row["data_class"] != request.data_class
            or row["transfer_purpose"] != request.transfer_purpose
        ):
            raise ToolReceiptConflict(
                "reconciliation request does not match pending reservation"
            )

    def reconcile_pending(
        self,
        request: ToolExecutionRequest,
        evidence: ToolEffectReconciliationEvidence,
        *,
        now: datetime | None = None,
    ) -> ToolExecutionReceipt:
        """Resolve one pending reservation without invoking the tool handler."""

        if not isinstance(request, ToolExecutionRequest):
            raise TypeError("request must be ToolExecutionRequest")
        if not isinstance(evidence, ToolEffectReconciliationEvidence):
            raise TypeError(
                "evidence must be ToolEffectReconciliationEvidence"
            )

        reconciled_at = (
            datetime.now(timezone.utc)
            if now is None
            else _utc(now, "now")
        )
        reconciled_at = max(reconciled_at, evidence.observed_at)
        request_digest = _canonical_digest(_request_projection(request))
        evidence_digest = evidence.digest
        terminal_receipt_id = _terminal_receipt_id(request, evidence)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(request)
                if row is None:
                    raise ToolEffectReconciliationError(
                        "cannot reconcile unknown reservation"
                    )
                self._assert_exact_identity(row, request)

                prior = self._connection.execute(
                    """
                    SELECT * FROM tool_effect_reconciliation
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                    """,
                    (
                        self.namespace,
                        request.tenant_id,
                        request.operation_id,
                        request.idempotency_key,
                    ),
                ).fetchone()
                if prior is not None:
                    if (
                        prior["request_digest"] != request_digest
                        or prior["evidence_digest"] != evidence_digest
                        or prior["terminal_receipt_id"]
                        != terminal_receipt_id
                    ):
                        raise ToolEffectReconciliationConflict(
                            "reservation was reconciled with different evidence"
                        )
                    self._connection.execute("COMMIT")
                    reservation = self.get(
                        tenant_id=request.tenant_id,
                        operation_id=request.operation_id,
                        idempotency_key=request.idempotency_key,
                    )
                    if reservation is None or reservation.receipt is None:
                        raise ToolEffectReconciliationConflict(
                            "reconciliation record lost terminal receipt"
                        )
                    return reservation.receipt

                if row["state"] == "committed":
                    raise ToolEffectReconciliationConflict(
                        "normally committed receipt cannot be reclassified"
                    )
                if row["state"] != "pending":
                    raise ToolEffectReconciliationError(
                        "reservation is not pending"
                    )

                started_at = _parse_time(row["reserved_at"], "reserved_at")
                finished_at = max(started_at, evidence.observed_at)
                if evidence.decision == "effect_committed":
                    status = ToolExecutionStatus.SUCCEEDED
                    result_ref = evidence.result_ref
                    error_code = None
                    compensation_ref = None
                elif evidence.decision == "effect_absent":
                    status = ToolExecutionStatus.FAILED
                    result_ref = None
                    error_code = "reconciled_effect_absent"
                    compensation_ref = None
                else:
                    status = ToolExecutionStatus.FAILED
                    result_ref = None
                    error_code = "reconciled_effect_compensated"
                    compensation_ref = evidence.compensation_ref

                receipt = ToolExecutionReceipt(
                    receipt_id=terminal_receipt_id,
                    request_id=request.request_id,
                    operation_id=request.operation_id,
                    execution_id=request.execution_id,
                    turn_id=request.turn_id,
                    call_id=request.call_id,
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=status,
                    started_at=started_at,
                    finished_at=finished_at,
                    result_ref=result_ref,
                    error_code=error_code,
                    approval_ref=request.approval_ref,
                    compensation_ref=compensation_ref,
                    data_class=request.data_class,
                    transfer_purpose=request.transfer_purpose,
                    governance_decision_ref=(
                        "reconciliation:" + evidence_digest
                    ),
                    postcondition_verified=False,
                    metered_tool_calls=0,
                )
                receipt_json = json.dumps(
                    receipt.as_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                )
                evidence_json = json.dumps(
                    evidence.as_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                )

                cursor = self._connection.execute(
                    """
                    UPDATE tool_execution_receipt
                    SET state = 'committed',
                        receipt_json = ?,
                        completed_at = ?
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                      AND state = 'pending'
                    """,
                    (
                        receipt_json,
                        finished_at.isoformat(),
                        self.namespace,
                        request.tenant_id,
                        request.operation_id,
                        request.idempotency_key,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ToolEffectReconciliationConflict(
                        "pending reservation changed during reconciliation"
                    )
                self._connection.execute(
                    """
                    INSERT INTO tool_effect_reconciliation(
                        namespace,
                        tenant_id,
                        operation_id,
                        idempotency_key,
                        request_digest,
                        evidence_digest,
                        evidence_json,
                        terminal_receipt_id,
                        reconciled_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        request.tenant_id,
                        request.operation_id,
                        request.idempotency_key,
                        request_digest,
                        evidence_digest,
                        evidence_json,
                        terminal_receipt_id,
                        reconciled_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return receipt
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def reconciliation_evidence(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> ToolEffectReconciliationEvidence | None:
        """Return the durable independent evidence for a reconciled effect."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT evidence_json
                FROM tool_effect_reconciliation
                WHERE namespace = ?
                  AND tenant_id = ?
                  AND operation_id = ?
                  AND idempotency_key = ?
                """,
                (
                    self.namespace,
                    tenant_id,
                    operation_id,
                    idempotency_key,
                ),
            ).fetchone()
            if row is None:
                return None
            try:
                payload = json.loads(row["evidence_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise ToolEffectReconciliationError(
                    "stored reconciliation evidence is corrupt"
                ) from exc
            if not isinstance(payload, dict):
                raise ToolEffectReconciliationError(
                    "stored reconciliation evidence must be an object"
                )
            return ToolEffectReconciliationEvidence(
                decision=payload["decision"],
                observer_id=payload["observer_id"],
                authority_ref=payload["authority_ref"],
                evidence_refs=tuple(payload["evidence_refs"]),
                observed_at=_parse_time(
                    payload["observed_at"],
                    "observed_at",
                ),
                result_ref=payload.get("result_ref"),
                compensation_ref=payload.get("compensation_ref"),
                note=payload.get("note"),
                schema_version=payload["schema_version"],
            )

    def reconciliation_receipt(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> ToolEffectReconciliationReceipt | None:
        """Return the durable binding between request, evidence and receipt."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT request_digest, evidence_digest,
                       terminal_receipt_id, reconciled_at
                FROM tool_effect_reconciliation
                WHERE namespace = ?
                  AND tenant_id = ?
                  AND operation_id = ?
                  AND idempotency_key = ?
                """,
                (
                    self.namespace,
                    tenant_id,
                    operation_id,
                    idempotency_key,
                ),
            ).fetchone()
            if row is None:
                return None
            return ToolEffectReconciliationReceipt(
                request_digest=row["request_digest"],
                evidence_digest=row["evidence_digest"],
                terminal_receipt_id=row["terminal_receipt_id"],
                reconciled_at=_parse_time(
                    row["reconciled_at"],
                    "reconciled_at",
                ),
            )


__all__ = [
    "ReconciliableToolReceiptStore",
    "ToolEffectReconciliationConflict",
    "ToolEffectReconciliationError",
    "ToolEffectReconciliationEvidence",
    "ToolEffectReconciliationReceipt",
]
