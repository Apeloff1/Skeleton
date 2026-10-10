"""Durable compensation/saga orchestration for privileged tool execution.

The saga layer composes the canonical :class:`AsyncToolRuntime`; it never
executes side effects directly. Every forward and compensation action therefore
inherits the tool runtime's authorization, schema, governance, budget,
idempotency, and durable receipt boundaries.

Saga durability stores only identities, digests, receipt ids, and progress.
Raw tool arguments and results are never persisted by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable
from uuid import UUID, uuid4

from skeleton.skills.tool_contract import (
    ToolAuthorityClass,
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionReceipt,
    ToolExecutionStatus,
    ToolIdempotencyMode,
    ToolManifest,
    ToolSideEffectClass,
    approval_ref_for_request,
    validate_tool_arguments,
)
from skeleton.skills.tool_runtime import AsyncToolRuntime


TOOL_SAGA_SCHEMA_VERSION = 1
_TERMINAL_STATES = frozenset(
    {
        "succeeded",
        "failed",
        "compensated",
        "compensation_failed",
    }
)


class ToolSagaError(RuntimeError):
    """Base saga orchestration failure."""


class ToolSagaConflict(ToolSagaError):
    """A saga identity was reused with a different plan or progress."""


class ToolSagaDenied(ToolSagaError):
    """A saga plan is unsafe or violates the canonical tool contract."""


class ToolSagaInDoubt(ToolSagaError):
    """Saga progress cannot safely continue without explicit recovery."""


class ToolSagaStatus(str, Enum):
    RUNNING = "running"
    COMPENSATING = "compensating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"


@dataclass(frozen=True, slots=True)
class ToolSagaStep:
    """One forward tool request plus its optional compensation request."""

    forward: ToolExecutionRequest
    compensation: ToolExecutionRequest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.forward, ToolExecutionRequest):
            raise TypeError("forward must be ToolExecutionRequest")
        if self.compensation is not None and not isinstance(
            self.compensation,
            ToolExecutionRequest,
        ):
            raise TypeError("compensation must be ToolExecutionRequest or None")


@dataclass(frozen=True, slots=True)
class ToolSagaReceipt:
    """Durable, content-bound saga progress/terminal receipt."""

    saga_id: str
    tenant_id: str
    operation_id: str
    plan_digest: str
    status: ToolSagaStatus
    next_forward: int
    next_compensation: int
    forward_receipt_ids: tuple[str, ...]
    compensation_receipt_ids: tuple[str, ...]
    compensation_failures: tuple[str, ...] = ()
    failed_step_index: int | None = None
    error_code: str | None = None
    schema_version: int = TOOL_SAGA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.saga_id, "saga_id")
        _text(self.tenant_id, "tenant_id")
        _uuid(self.operation_id, "operation_id")
        _digest(self.plan_digest, "plan_digest")
        try:
            object.__setattr__(self, "status", ToolSagaStatus(self.status))
        except ValueError as exc:
            raise ToolSagaError("invalid saga status") from exc
        if self.next_forward < 0:
            raise ToolSagaError("next_forward must be non-negative")
        if self.next_compensation < -1:
            raise ToolSagaError("next_compensation must be >= -1")
        for receipt_id in self.forward_receipt_ids + self.compensation_receipt_ids:
            _uuid(receipt_id, "receipt_id")
        for failure in self.compensation_failures:
            _text(failure, "compensation_failure", max_length=512)
        if self.failed_step_index is not None and self.failed_step_index < 0:
            raise ToolSagaError("failed_step_index must be non-negative")
        if self.error_code is not None:
            _text(self.error_code, "error_code", max_length=512)
        if self.schema_version != TOOL_SAGA_SCHEMA_VERSION:
            raise ToolSagaError("unsupported saga schema version")

    @property
    def terminal(self) -> bool:
        return self.status.value in _TERMINAL_STATES

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "saga_id": self.saga_id,
            "tenant_id": self.tenant_id,
            "operation_id": self.operation_id,
            "plan_digest": self.plan_digest,
            "status": self.status.value,
            "next_forward": self.next_forward,
            "next_compensation": self.next_compensation,
            "forward_receipt_ids": list(self.forward_receipt_ids),
            "compensation_receipt_ids": list(self.compensation_receipt_ids),
            "compensation_failures": list(self.compensation_failures),
            "failed_step_index": self.failed_step_index,
            "error_code": self.error_code,
        }


def _text(value: object, field: str, *, max_length: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ToolSagaError(f"{field} must be normalized non-empty text")
    if len(value) > max_length:
        raise ToolSagaError(f"{field} exceeds maximum length")
    return value


def _uuid(value: object, field: str) -> str:
    raw = _text(value, field, max_length=64)
    try:
        parsed = UUID(raw)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ToolSagaError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != raw:
        raise ToolSagaError(f"{field} must be a canonical UUID")
    return raw


def _digest(value: object, field: str) -> str:
    raw = _text(value, field, max_length=64)
    if len(raw) != 64 or any(ch not in "0123456789abcdef" for ch in raw):
        raise ToolSagaError(f"{field} must be lowercase sha256")
    return raw


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _request_projection(request: ToolExecutionRequest) -> dict[str, object]:
    return {
        "schema_version": request.schema_version,
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


def _normalize_steps(steps: Iterable[ToolSagaStep]) -> tuple[ToolSagaStep, ...]:
    normalized = tuple(steps)
    if not normalized:
        raise ToolSagaDenied("saga requires at least one step")
    if len(normalized) > 256:
        raise ToolSagaDenied("saga exceeds maximum step count")
    if any(not isinstance(step, ToolSagaStep) for step in normalized):
        raise TypeError("steps must contain ToolSagaStep values")

    tenant_id = normalized[0].forward.tenant_id
    operation_id = normalized[0].forward.operation_id
    idempotency_keys: set[str] = set()

    for step in normalized:
        requests = (step.forward,) + (
            (step.compensation,) if step.compensation is not None else ()
        )
        for request in requests:
            assert request is not None
            if request.tenant_id != tenant_id:
                raise ToolSagaDenied("all saga requests must share tenant_id")
            if request.operation_id != operation_id:
                raise ToolSagaDenied("all saga requests must share operation_id")
            if request.idempotency_key in idempotency_keys:
                raise ToolSagaDenied(
                    "saga requests must use distinct idempotency keys"
                )
            idempotency_keys.add(request.idempotency_key)
    return normalized


def tool_saga_plan_digest(steps: Iterable[ToolSagaStep]) -> str:
    """Digest a saga plan without persisting raw arguments or results."""

    normalized = _normalize_steps(steps)
    return _canonical_digest(
        {
            "schema_version": TOOL_SAGA_SCHEMA_VERSION,
            "steps": [
                {
                    "forward": _request_projection(step.forward),
                    "compensation": (
                        None
                        if step.compensation is None
                        else _request_projection(step.compensation)
                    ),
                }
                for step in normalized
            ],
        }
    )


def _receipt_matches_request(
    receipt: ToolExecutionReceipt,
    request: ToolExecutionRequest,
) -> bool:
    return (
        receipt.request_id == request.request_id
        and receipt.operation_id == request.operation_id
        and receipt.execution_id == request.execution_id
        and receipt.turn_id == request.turn_id
        and receipt.call_id == request.call_id
        and receipt.tenant_id == request.tenant_id
        and receipt.tool_id == request.tool_id
        and receipt.idempotency_key == request.idempotency_key
        and receipt.arguments_digest == request.arguments_digest
        and receipt.data_class == request.data_class
        and receipt.transfer_purpose == request.transfer_purpose
    )


def _approval_is_bound(
    manifest: ToolManifest,
    request: ToolExecutionRequest,
) -> bool:
    if not manifest.approval_required:
        return True
    return request.approval_ref == approval_ref_for_request(request)


def _previous_compensation(
    steps: tuple[ToolSagaStep, ...],
    start: int,
) -> int:
    for index in range(start, -1, -1):
        if steps[index].compensation is not None:
            return index
    return -1


class SQLiteToolSagaStore:
    """Crash-stable saga progress authority with explicit orphan recovery."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "tool_saga",
    ) -> None:
        self.namespace = _text(str(namespace), "namespace", max_length=128)
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tool_saga (
                    namespace TEXT NOT NULL,
                    saga_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    next_forward INTEGER NOT NULL,
                    next_compensation INTEGER NOT NULL,
                    forward_receipts_json TEXT NOT NULL,
                    compensation_receipts_json TEXT NOT NULL,
                    compensation_failures_json TEXT NOT NULL,
                    failed_step_index INTEGER,
                    error_code TEXT,
                    owner_token TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, saga_id)
                );
                CREATE INDEX IF NOT EXISTS idx_tool_saga_state
                ON tool_saga(namespace, state, updated_at);
                """
            )

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> ToolSagaReceipt:
        def strings(field: str) -> tuple[str, ...]:
            value = json.loads(row[field])
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                raise ToolSagaError(f"{field} is corrupt")
            return tuple(value)

        return ToolSagaReceipt(
            saga_id=row["saga_id"],
            tenant_id=row["tenant_id"],
            operation_id=row["operation_id"],
            plan_digest=row["plan_digest"],
            status=ToolSagaStatus(row["state"]),
            next_forward=int(row["next_forward"]),
            next_compensation=int(row["next_compensation"]),
            forward_receipt_ids=strings("forward_receipts_json"),
            compensation_receipt_ids=strings("compensation_receipts_json"),
            compensation_failures=strings("compensation_failures_json"),
            failed_step_index=(
                None
                if row["failed_step_index"] is None
                else int(row["failed_step_index"])
            ),
            error_code=row["error_code"],
        )

    def _select(self, saga_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM tool_saga
            WHERE namespace = ? AND saga_id = ?
            """,
            (self.namespace, saga_id),
        ).fetchone()

    @staticmethod
    def _assert_identity(
        row: sqlite3.Row,
        *,
        tenant_id: str,
        operation_id: str,
        plan_digest: str,
    ) -> None:
        if (
            row["tenant_id"] != tenant_id
            or row["operation_id"] != operation_id
            or row["plan_digest"] != plan_digest
        ):
            raise ToolSagaConflict(
                "saga_id replayed with different tenant, operation, or plan"
            )

    def claim(
        self,
        *,
        saga_id: str,
        tenant_id: str,
        operation_id: str,
        plan_digest: str,
        owner_token: str,
        now: datetime | None = None,
    ) -> ToolSagaReceipt:
        _uuid(saga_id, "saga_id")
        _text(tenant_id, "tenant_id")
        _uuid(operation_id, "operation_id")
        _digest(plan_digest, "plan_digest")
        _uuid(owner_token, "owner_token")
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select(saga_id)
                if row is None:
                    self._connection.execute(
                        """
                        INSERT INTO tool_saga(
                            namespace, saga_id, tenant_id, operation_id,
                            plan_digest, state, next_forward,
                            next_compensation, forward_receipts_json,
                            compensation_receipts_json,
                            compensation_failures_json, failed_step_index,
                            error_code, owner_token, updated_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, 'running', 0, -1,
                            '[]', '[]', '[]', NULL, NULL, ?, ?
                        )
                        """,
                        (
                            self.namespace,
                            saga_id,
                            tenant_id,
                            operation_id,
                            plan_digest,
                            owner_token,
                            instant.isoformat(),
                        ),
                    )
                    row = self._select(saga_id)
                    assert row is not None
                    self._connection.execute("COMMIT")
                    return self._snapshot(row)

                self._assert_identity(
                    row,
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    plan_digest=plan_digest,
                )
                if row["state"] in _TERMINAL_STATES:
                    self._connection.execute("COMMIT")
                    return self._snapshot(row)
                current_owner = row["owner_token"]
                if current_owner not in {None, owner_token}:
                    raise ToolSagaInDoubt(
                        "saga has a different durable execution owner"
                    )
                if current_owner is None:
                    self._connection.execute(
                        """
                        UPDATE tool_saga
                        SET owner_token = ?, updated_at = ?
                        WHERE namespace = ? AND saga_id = ?
                        """,
                        (
                            owner_token,
                            instant.isoformat(),
                            self.namespace,
                            saga_id,
                        ),
                    )
                row = self._select(saga_id)
                assert row is not None
                self._connection.execute("COMMIT")
                return self._snapshot(row)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def recover_orphaned(
        self,
        *,
        saga_id: str,
        tenant_id: str,
        operation_id: str,
        plan_digest: str,
        expected_owner_token: str,
        now: datetime | None = None,
    ) -> ToolSagaReceipt:
        """Release a crashed saga owner after the caller proves it is gone.

        This method deliberately cannot determine process liveness. Calling it
        while a prior owner is still executing can violate saga serialization;
        callers must establish exclusive recovery authority first.
        """

        _uuid(saga_id, "saga_id")
        expected_owner_token = _uuid(
            expected_owner_token,
            "expected_owner_token",
        )
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select(saga_id)
                if row is None:
                    raise ToolSagaConflict("cannot recover unknown saga")
                self._assert_identity(
                    row,
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    plan_digest=plan_digest,
                )
                if row["state"] not in _TERMINAL_STATES:
                    current_owner = row["owner_token"]
                    if current_owner is not None and current_owner != expected_owner_token:
                        raise ToolSagaInDoubt(
                            "saga owner changed before orphan recovery"
                        )
                    if current_owner is not None:
                        cursor = self._connection.execute(
                            """
                            UPDATE tool_saga
                            SET owner_token = NULL, updated_at = ?
                            WHERE namespace = ? AND saga_id = ?
                              AND owner_token = ?
                            """,
                            (
                                instant.isoformat(),
                                self.namespace,
                                saga_id,
                                expected_owner_token,
                            ),
                        )
                        if cursor.rowcount != 1:
                            raise ToolSagaInDoubt(
                                "saga owner changed during orphan recovery"
                            )
                row = self._select(saga_id)
                assert row is not None
                self._connection.execute("COMMIT")
                return self._snapshot(row)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def record_forward(
        self,
        *,
        saga_id: str,
        owner_token: str,
        index: int,
        step_count: int,
        receipt: ToolExecutionReceipt,
        compensation_target: int,
        now: datetime | None = None,
    ) -> ToolSagaReceipt:
        if index < 0 or index >= step_count:
            raise ToolSagaConflict("forward index is outside saga plan")
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select(saga_id)
                if row is None:
                    raise ToolSagaConflict("unknown saga")
                if row["owner_token"] != owner_token:
                    raise ToolSagaInDoubt("saga execution owner changed")
                if row["state"] != ToolSagaStatus.RUNNING.value:
                    raise ToolSagaConflict("saga is not accepting forward progress")
                if int(row["next_forward"]) != index:
                    raise ToolSagaConflict("forward progress index drift")

                receipts = json.loads(row["forward_receipts_json"])
                receipts.append(receipt.receipt_id)
                if receipt.status is ToolExecutionStatus.SUCCEEDED:
                    next_forward = index + 1
                    state = (
                        ToolSagaStatus.SUCCEEDED.value
                        if next_forward == step_count
                        else ToolSagaStatus.RUNNING.value
                    )
                    next_compensation = -1
                    failed_step = None
                    error_code = None
                else:
                    next_forward = index
                    failed_step = index
                    error_code = receipt.error_code or receipt.status.value
                    next_compensation = compensation_target
                    state = (
                        ToolSagaStatus.COMPENSATING.value
                        if compensation_target >= 0
                        else ToolSagaStatus.FAILED.value
                    )

                terminal = state in _TERMINAL_STATES
                self._connection.execute(
                    """
                    UPDATE tool_saga
                    SET state = ?, next_forward = ?,
                        next_compensation = ?,
                        forward_receipts_json = ?,
                        failed_step_index = ?, error_code = ?,
                        owner_token = ?, updated_at = ?
                    WHERE namespace = ? AND saga_id = ?
                    """,
                    (
                        state,
                        next_forward,
                        next_compensation,
                        json.dumps(receipts, separators=(",", ":")),
                        failed_step,
                        error_code,
                        None if terminal else owner_token,
                        instant.isoformat(),
                        self.namespace,
                        saga_id,
                    ),
                )
                row = self._select(saga_id)
                assert row is not None
                self._connection.execute("COMMIT")
                return self._snapshot(row)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def record_compensation(
        self,
        *,
        saga_id: str,
        owner_token: str,
        index: int,
        receipt: ToolExecutionReceipt,
        next_compensation: int,
        now: datetime | None = None,
    ) -> ToolSagaReceipt:
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select(saga_id)
                if row is None:
                    raise ToolSagaConflict("unknown saga")
                if row["owner_token"] != owner_token:
                    raise ToolSagaInDoubt("saga execution owner changed")
                if row["state"] != ToolSagaStatus.COMPENSATING.value:
                    raise ToolSagaConflict("saga is not compensating")
                if int(row["next_compensation"]) != index:
                    raise ToolSagaConflict("compensation progress index drift")

                receipts = json.loads(row["compensation_receipts_json"])
                failures = json.loads(row["compensation_failures_json"])
                receipts.append(receipt.receipt_id)
                if receipt.status is not ToolExecutionStatus.SUCCEEDED:
                    failures.append(
                        f"{index}:{receipt.error_code or receipt.status.value}"
                    )

                if next_compensation >= 0:
                    state = ToolSagaStatus.COMPENSATING.value
                    owner = owner_token
                else:
                    state = (
                        ToolSagaStatus.COMPENSATION_FAILED.value
                        if failures
                        else ToolSagaStatus.COMPENSATED.value
                    )
                    owner = None

                self._connection.execute(
                    """
                    UPDATE tool_saga
                    SET state = ?, next_compensation = ?,
                        compensation_receipts_json = ?,
                        compensation_failures_json = ?,
                        owner_token = ?, updated_at = ?
                    WHERE namespace = ? AND saga_id = ?
                    """,
                    (
                        state,
                        next_compensation,
                        json.dumps(receipts, separators=(",", ":")),
                        json.dumps(failures, separators=(",", ":")),
                        owner,
                        instant.isoformat(),
                        self.namespace,
                        saga_id,
                    ),
                )
                row = self._select(saga_id)
                assert row is not None
                self._connection.execute("COMMIT")
                return self._snapshot(row)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get(self, saga_id: str) -> ToolSagaReceipt | None:
        _uuid(saga_id, "saga_id")
        with self._lock:
            row = self._select(saga_id)
            return None if row is None else self._snapshot(row)

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class AsyncToolSagaRuntime:
    """Execute a durable sequence and compensate failures in reverse order."""

    def __init__(
        self,
        tool_runtime: AsyncToolRuntime,
        saga_store: SQLiteToolSagaStore,
    ) -> None:
        if not isinstance(tool_runtime, AsyncToolRuntime):
            raise TypeError("tool_runtime must be AsyncToolRuntime")
        if not isinstance(saga_store, SQLiteToolSagaStore):
            raise TypeError("saga_store must be SQLiteToolSagaStore")
        if tool_runtime.receipt_store is None:
            raise ToolSagaDenied(
                "durable tool receipt store is required for saga execution"
            )
        self.tool_runtime = tool_runtime
        self.saga_store = saga_store

    async def _preflight(
        self,
        steps: tuple[ToolSagaStep, ...],
    ) -> None:
        for index, step in enumerate(steps):
            manifest = await self.tool_runtime.manifest(step.forward.tool_id)
            validate_tool_arguments(
                manifest.input_schema,
                step.forward.arguments,
            )
            if not _approval_is_bound(manifest, step.forward):
                raise ToolSagaDenied(
                    f"step {index} forward approval is missing or mismatched"
                )
            if manifest.effect is ToolEffect.IRREVERSIBLE:
                raise ToolSagaDenied(
                    f"step {index} irreversible tools cannot enter an automatic saga"
                )
            if manifest.effect is ToolEffect.READ_ONLY:
                if manifest.side_effect_class is not ToolSideEffectClass.NONE:
                    raise ToolSagaDenied(
                        f"step {index} read-only effect conflicts with side-effect class"
                    )
                if step.compensation is not None:
                    raise ToolSagaDenied(
                        f"step {index} read-only tool cannot declare saga compensation"
                    )
                continue

            if manifest.side_effect_class not in {
                ToolSideEffectClass.LOCAL_REVERSIBLE,
                ToolSideEffectClass.EXTERNAL_REVERSIBLE,
            }:
                raise ToolSagaDenied(
                    f"step {index} reversible effect lacks reversible side-effect class"
                )
            if manifest.idempotency_mode is not ToolIdempotencyMode.COMPENSATABLE:
                raise ToolSagaDenied(
                    f"step {index} reversible saga tool must be compensatable"
                )
            if manifest.compensation_tool_id is None or step.compensation is None:
                raise ToolSagaDenied(
                    f"step {index} reversible saga tool requires compensation"
                )
            if step.compensation.tool_id != manifest.compensation_tool_id:
                raise ToolSagaDenied(
                    f"step {index} compensation tool does not match manifest"
                )

            compensation_manifest = await self.tool_runtime.manifest(
                step.compensation.tool_id
            )
            validate_tool_arguments(
                compensation_manifest.input_schema,
                step.compensation.arguments,
            )
            if compensation_manifest.effect is not ToolEffect.REVERSIBLE:
                raise ToolSagaDenied(
                    f"step {index} compensation tool must be reversible"
                )
            if compensation_manifest.authority_class is ToolAuthorityClass.READ:
                raise ToolSagaDenied(
                    f"step {index} compensation tool requires mutation authority"
                )
            if compensation_manifest.side_effect_class not in {
                ToolSideEffectClass.LOCAL_REVERSIBLE,
                ToolSideEffectClass.EXTERNAL_REVERSIBLE,
            }:
                raise ToolSagaDenied(
                    f"step {index} compensation side-effect class is unsafe"
                )
            if compensation_manifest.idempotency_mode is ToolIdempotencyMode.NOT_REQUIRED:
                raise ToolSagaDenied(
                    f"step {index} compensation tool must be replay-safe"
                )
            if not _approval_is_bound(
                compensation_manifest,
                step.compensation,
            ):
                raise ToolSagaDenied(
                    f"step {index} compensation approval is missing or mismatched"
                )

    async def recover_orphaned(
        self,
        saga_id: str,
        steps: Iterable[ToolSagaStep],
        *,
        expected_owner_token: str,
        now: datetime | None = None,
    ) -> ToolSagaReceipt:
        """Explicitly release a crashed saga owner for a content-identical plan."""

        normalized = _normalize_steps(steps)
        await self._preflight(normalized)
        return self.saga_store.recover_orphaned(
            saga_id=saga_id,
            tenant_id=normalized[0].forward.tenant_id,
            operation_id=normalized[0].forward.operation_id,
            plan_digest=tool_saga_plan_digest(normalized),
            expected_owner_token=expected_owner_token,
            now=now,
        )

    async def execute(
        self,
        saga_id: str,
        steps: Iterable[ToolSagaStep],
        *,
        owner_token: str | None = None,
        now: datetime | None = None,
    ) -> ToolSagaReceipt:
        _uuid(saga_id, "saga_id")
        normalized = _normalize_steps(steps)
        await self._preflight(normalized)
        token = str(uuid4()) if owner_token is None else _uuid(
            owner_token,
            "owner_token",
        )
        snapshot = self.saga_store.claim(
            saga_id=saga_id,
            tenant_id=normalized[0].forward.tenant_id,
            operation_id=normalized[0].forward.operation_id,
            plan_digest=tool_saga_plan_digest(normalized),
            owner_token=token,
            now=now,
        )
        if snapshot.terminal:
            return snapshot

        while not snapshot.terminal:
            if snapshot.status is ToolSagaStatus.RUNNING:
                index = snapshot.next_forward
                if index >= len(normalized):
                    raise ToolSagaConflict("forward progress exceeds saga plan")
                step = normalized[index]
                receipt = await self.tool_runtime.execute(
                    step.forward,
                    now=now,
                )
                if not _receipt_matches_request(receipt, step.forward):
                    raise ToolSagaConflict(
                        f"forward step {index} receipt is not bound to request"
                    )
                if (
                    receipt.status is ToolExecutionStatus.DENIED
                    and receipt.error_code == "execution_in_doubt"
                ):
                    raise ToolSagaInDoubt(
                        f"forward step {index} tool execution is in doubt"
                    )

                if receipt.status is ToolExecutionStatus.FAILED:
                    if receipt.error_code in {
                        "reconciled_effect_absent",
                        "reconciled_effect_compensated",
                    }:
                        # Independent reconciliation already proved there is no
                        # uncompensated effect at this step. Compensating it
                        # again can create a new side effect, so continue only
                        # with prior successfully committed saga steps.
                        compensation_target = _previous_compensation(
                            normalized,
                            index - 1,
                        )
                    else:
                        compensation_target = (
                            index
                            if step.compensation is not None
                            else _previous_compensation(normalized, index - 1)
                        )
                elif receipt.status is ToolExecutionStatus.DENIED:
                    compensation_target = _previous_compensation(
                        normalized,
                        index - 1,
                    )
                else:
                    compensation_target = -1

                snapshot = self.saga_store.record_forward(
                    saga_id=saga_id,
                    owner_token=token,
                    index=index,
                    step_count=len(normalized),
                    receipt=receipt,
                    compensation_target=compensation_target,
                    now=now,
                )
                continue

            if snapshot.status is ToolSagaStatus.COMPENSATING:
                index = snapshot.next_compensation
                if index < 0 or index >= len(normalized):
                    raise ToolSagaConflict(
                        "compensation progress exceeds saga plan"
                    )
                request = normalized[index].compensation
                if request is None:
                    raise ToolSagaConflict(
                        "compensation cursor points at non-compensatable step"
                    )
                receipt = await self.tool_runtime.execute(
                    request,
                    now=now,
                )
                if not _receipt_matches_request(receipt, request):
                    raise ToolSagaConflict(
                        f"compensation step {index} receipt is not bound to request"
                    )
                if (
                    receipt.status is ToolExecutionStatus.DENIED
                    and receipt.error_code == "execution_in_doubt"
                ):
                    raise ToolSagaInDoubt(
                        f"compensation step {index} tool execution is in doubt"
                    )
                snapshot = self.saga_store.record_compensation(
                    saga_id=saga_id,
                    owner_token=token,
                    index=index,
                    receipt=receipt,
                    next_compensation=_previous_compensation(
                        normalized,
                        index - 1,
                    ),
                    now=now,
                )
                continue

            raise ToolSagaConflict(
                f"non-terminal saga has unsupported state {snapshot.status.value}"
            )

        return snapshot


__all__ = [
    "AsyncToolSagaRuntime",
    "SQLiteToolSagaStore",
    "TOOL_SAGA_SCHEMA_VERSION",
    "ToolSagaConflict",
    "ToolSagaDenied",
    "ToolSagaError",
    "ToolSagaInDoubt",
    "ToolSagaReceipt",
    "ToolSagaStatus",
    "ToolSagaStep",
    "tool_saga_plan_digest",
]
