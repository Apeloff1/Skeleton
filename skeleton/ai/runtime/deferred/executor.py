"""Bounded execution kernel for the deferred 165-volume capability registry.

The kernel intentionally separates implementation ownership from execution
authority.  A volume must be enabled through the evidence state machine, have an
explicit host-registered handler, and have an explicit budget before execution.
Operation IDs are terminal: successful calls replay their receipt without
re-running effects, while failed calls cannot be retried under the same ID.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import threading
from typing import Any, Callable, Mapping

from .contracts import (
    Budget,
    BudgetLedger,
    CapabilityRegistry,
    canonical_json,
    sha256_json,
)

_VOLUME_RE = re.compile(r"^VOL-\d{3}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


def _units(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _validate_json(value: Any, *, depth: int = 0) -> None:
    if depth > 64:
        raise ValueError("JSON value exceeds maximum nesting depth")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("JSON numbers must be finite")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            _validate_json(child, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _validate_json(child, depth=depth + 1)
        return
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def _strict_json(value: Any) -> str:
    _validate_json(value)
    return canonical_json(value)


@dataclass(frozen=True, slots=True)
class DeferredInvocation:
    operation_id: str
    volume_id: str
    spec_digest: str
    authority_digest: str
    payload_digest: str
    cost_units: int = 0
    latency_ms: int = 0

    def __post_init__(self) -> None:
        operation_id=_text(self.operation_id, "operation_id")
        if len(operation_id)>256:
            raise ValueError("operation_id must be at most 256 characters")
        if any(ord(ch)<32 for ch in operation_id):
            raise ValueError("operation_id must not contain control characters")
        object.__setattr__(self, "operation_id", operation_id)
        volume_id = _text(self.volume_id, "volume_id")
        if not _VOLUME_RE.fullmatch(volume_id):
            raise ValueError("volume_id must be VOL-NNN")
        object.__setattr__(self, "volume_id", volume_id)
        object.__setattr__(
            self,
            "spec_digest",
            _sha256(self.spec_digest, "spec_digest"),
        )
        object.__setattr__(
            self,
            "authority_digest",
            _sha256(self.authority_digest, "authority_digest"),
        )
        object.__setattr__(
            self,
            "payload_digest",
            _sha256(self.payload_digest, "payload_digest"),
        )
        object.__setattr__(
            self,
            "cost_units",
            _units(self.cost_units, "cost_units"),
        )
        object.__setattr__(
            self,
            "latency_ms",
            _units(self.latency_ms, "latency_ms"),
        )

    @property
    def fingerprint(self) -> str:
        return sha256_json(
            {
                "operation_id": self.operation_id,
                "volume_id": self.volume_id,
                "spec_digest": self.spec_digest,
                "authority_digest": self.authority_digest,
                "payload_digest": self.payload_digest,
                "cost_units": self.cost_units,
                "latency_ms": self.latency_ms,
            }
        )


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    operation_id: str
    volume_id: str
    spec_digest: str
    authority_digest: str
    payload_digest: str
    handler_identity: str
    result_digest: str
    attempt: int
    cost_units: int
    latency_ms: int
    status: str = "succeeded"

    def __post_init__(self) -> None:
        if self.status != "succeeded":
            raise ValueError("ExecutionReceipt status must be succeeded")
        for name in ("operation_id", "volume_id", "handler_identity"):
            _text(getattr(self, name), name)
        for name in ("spec_digest", "authority_digest", "payload_digest", "result_digest"):
            _sha256(getattr(self, name), name)
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        _units(self.cost_units, "cost_units")
        _units(self.latency_ms, "latency_ms")

    def as_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "volume_id": self.volume_id,
            "spec_digest": self.spec_digest,
            "authority_digest": self.authority_digest,
            "payload_digest": self.payload_digest,
            "handler_identity": self.handler_identity,
            "result_digest": self.result_digest,
            "attempt": self.attempt,
            "cost_units": self.cost_units,
            "latency_ms": self.latency_ms,
            "status": self.status,
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class FailureReceipt:
    operation_id: str
    volume_id: str
    spec_digest: str
    authority_digest: str
    payload_digest: str
    handler_identity: str
    attempt: int
    cost_units: int
    latency_ms: int
    error_type: str
    error_digest: str
    status: str = "failed"

    def __post_init__(self) -> None:
        if self.status != "failed":
            raise ValueError("FailureReceipt status must be failed")
        for name in (
            "operation_id",
            "volume_id",
            "handler_identity",
            "error_type",
        ):
            _text(getattr(self, name), name)
        for name in ("spec_digest", "authority_digest", "payload_digest", "error_digest"):
            _sha256(getattr(self, name), name)
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        _units(self.cost_units, "cost_units")
        _units(self.latency_ms, "latency_ms")

    def as_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "volume_id": self.volume_id,
            "spec_digest": self.spec_digest,
            "authority_digest": self.authority_digest,
            "payload_digest": self.payload_digest,
            "handler_identity": self.handler_identity,
            "attempt": self.attempt,
            "cost_units": self.cost_units,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "error_digest": self.error_digest,
            "status": self.status,
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    receipt: ExecutionReceipt
    result: Any

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, ExecutionReceipt):
            raise TypeError("receipt must be ExecutionReceipt")
        result_json=_strict_json(self.result)
        result_digest=hashlib.sha256(result_json.encode("utf-8")).hexdigest()
        if result_digest!=self.receipt.result_digest:
            raise ValueError("execution outcome result digest mismatch")


class DeferredExecutionError(RuntimeError):
    def __init__(self, message: str, receipt: FailureReceipt) -> None:
        super().__init__(message)
        self.receipt = receipt


@dataclass(frozen=True, slots=True)
class _Handler:
    identity: str
    fn: Callable[[Mapping[str, Any]], Any]

    def __post_init__(self) -> None:
        _text(self.identity, "handler identity")
        if not callable(self.fn):
            raise TypeError("handler must be callable")


class DeferredExecutor:
    """Execute enabled deferred-volume operations with fail-closed receipts."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("registry must be CapabilityRegistry")
        self.registry = registry
        self._handlers: dict[str, _Handler] = {}
        self._budgets: dict[str, Budget] = {}
        self._payload_limits: dict[str, int] = {}
        self._result_limits: dict[str, int] = {}
        self._fingerprints: dict[str, str] = {}
        self._in_flight: set[str] = set()
        self._lock = threading.RLock()
        self._success: dict[str, ExecutionReceipt] = {}
        self._success_result_json: dict[str, str] = {}
        self._failure: dict[str, FailureReceipt] = {}

    def register_handler(
        self,
        volume_id: str,
        handler: Callable[[Mapping[str, Any]], Any],
        *,
        handler_identity: str,
    ) -> None:
        record = self.registry.get(volume_id)
        identity = _text(handler_identity, "handler_identity")
        if identity != record.spec.handler:
            raise ValueError(
                "handler identity must match canonical capability handler"
            )
        candidate = _Handler(identity=identity, fn=handler)
        with self._lock:
            prior = self._handlers.get(volume_id)
            if prior is not None:
                if prior.identity != candidate.identity or prior.fn is not handler:
                    raise ValueError("volume handler is already registered")
                return
            self._handlers[volume_id] = candidate

    def set_budget(
        self,
        volume_id: str,
        budget: Budget,
        *,
        max_payload_bytes: int = 262_144,
        max_result_bytes: int = 262_144,
    ) -> None:
        self.registry.get(volume_id)
        if not isinstance(budget, Budget):
            raise TypeError("budget must be Budget")
        if budget.max_attempts != 1:
            raise ValueError(
                "deferred operation budgets require max_attempts=1; "
                "retries need a new operation_id"
            )
        for name, value in (
            ("max_payload_bytes", max_payload_bytes),
            ("max_result_bytes", max_result_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        with self._lock:
            self._budgets[volume_id] = budget
            self._payload_limits[volume_id] = max_payload_bytes
            self._result_limits[volume_id] = max_result_bytes

    @staticmethod
    def digest_payload(payload: Mapping[str, Any]) -> str:
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        return hashlib.sha256(
            _strict_json(dict(payload)).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def authority_digest(record: Any) -> str:
        return sha256_json(
            {
                "volume_id": record.spec.volume_id,
                "spec_digest": record.spec.digest,
                "state": record.state,
                "evidence_digests": sorted(record.evidence),
            }
        )

    def prepare(
        self,
        volume_id: str,
        operation_id: str,
        payload: Mapping[str, Any],
        *,
        cost_units: int = 0,
        latency_ms: int = 0,
    ) -> DeferredInvocation:
        record = self.registry.get(volume_id)
        with self._lock:
            if record.state != "enabled":
                raise PermissionError(f"capability {volume_id} is not enabled")
            if volume_id not in self._handlers:
                raise PermissionError("no host-registered handler")
            if volume_id not in self._budgets:
                raise PermissionError("no explicit execution budget")
        return DeferredInvocation(
            operation_id=operation_id,
            volume_id=volume_id,
            spec_digest=record.spec.digest,
            authority_digest=self.authority_digest(record),
            payload_digest=self.digest_payload(payload),
            cost_units=cost_units,
            latency_ms=latency_ms,
        )

    def _assert_current_authority(
        self,
        invocation: DeferredInvocation,
    ) -> None:
        record = self.registry.get(invocation.volume_id)
        if record.spec.digest != invocation.spec_digest:
            raise PermissionError("capability spec digest drift")
        if self.authority_digest(record) != invocation.authority_digest:
            raise PermissionError("capability authority digest drift")
        if record.state != "enabled":
            raise PermissionError(
                f"capability {invocation.volume_id} is not enabled"
            )

    def _admit(
        self,
        invocation: DeferredInvocation,
        payload: Mapping[str, Any],
    ) -> tuple[_Handler, BudgetLedger, Mapping[str, Any]]:
        record = self.registry.get(invocation.volume_id)
        if record.spec.digest != invocation.spec_digest:
            raise PermissionError("capability spec digest drift")
        if self.authority_digest(record) != invocation.authority_digest:
            raise PermissionError("capability authority digest drift")
        if record.state != "enabled":
            raise PermissionError(
                f"capability {invocation.volume_id} is not enabled"
            )

        handler = self._handlers.get(invocation.volume_id)
        if handler is None:
            raise PermissionError("no host-registered handler")
        if handler.identity != record.spec.handler:
            raise PermissionError("registered handler identity drift")

        budget = self._budgets.get(invocation.volume_id)
        if budget is None:
            raise PermissionError("no explicit execution budget")

        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        payload_json = _strict_json(dict(payload))
        payload_bytes = payload_json.encode("utf-8")
        if len(payload_bytes) > self._payload_limits[invocation.volume_id]:
            raise RuntimeError("payload byte limit exceeded")
        payload_digest = hashlib.sha256(payload_bytes).hexdigest()
        if payload_digest != invocation.payload_digest:
            raise ValueError("payload digest mismatch")

        prior_fingerprint = self._fingerprints.get(invocation.operation_id)
        if prior_fingerprint is not None and prior_fingerprint != invocation.fingerprint:
            raise ValueError("operation identity collision")
        if invocation.operation_id in self._failure:
            raise DeferredExecutionError(
                "operation previously failed and is terminal",
                self._failure[invocation.operation_id],
            )

        ledger = BudgetLedger(budget)
        ledger.admit(
            cost_units=invocation.cost_units,
            latency_ms=invocation.latency_ms,
        )
        isolated = json.loads(payload_json)
        return handler, ledger, isolated

    def _record_terminal_failure(
        self,
        invocation: DeferredInvocation,
        *,
        handler: _Handler,
        ledger: BudgetLedger,
        exc: BaseException,
    ) -> FailureReceipt:
        """Record a content-bound terminal fence before propagating a failure."""
        error_material = {
            "type": type(exc).__name__,
            "message_digest": hashlib.sha256(
                str(exc).encode("utf-8")
            ).hexdigest(),
        }
        failure = FailureReceipt(
            operation_id=invocation.operation_id,
            volume_id=invocation.volume_id,
            spec_digest=invocation.spec_digest,
            authority_digest=invocation.authority_digest,
            payload_digest=invocation.payload_digest,
            handler_identity=handler.identity,
            attempt=ledger.attempts,
            cost_units=ledger.cost_units,
            latency_ms=ledger.latency_ms,
            error_type=type(exc).__name__,
            error_digest=sha256_json(error_material),
        )
        with self._lock:
            self._failure[invocation.operation_id] = failure
            self._in_flight.discard(invocation.operation_id)
        return failure

    def execute(
        self,
        invocation: DeferredInvocation,
        payload: Mapping[str, Any],
    ) -> ExecutionOutcome:
        if not isinstance(invocation, DeferredInvocation):
            raise TypeError("invocation must be DeferredInvocation")

        with self._lock:
            prior = self._success.get(invocation.operation_id)
            if prior is not None:
                if self._fingerprints.get(invocation.operation_id) != invocation.fingerprint:
                    raise ValueError("operation identity collision")
                if self.digest_payload(payload) != invocation.payload_digest:
                    raise ValueError("payload digest mismatch")
                self._assert_current_authority(invocation)
                return ExecutionOutcome(
                    receipt=prior,
                    result=json.loads(
                        self._success_result_json[invocation.operation_id]
                    ),
                )
            if invocation.operation_id in self._in_flight:
                raise RuntimeError("operation is already in flight")
            handler, ledger, isolated = self._admit(invocation, payload)
            self._fingerprints[invocation.operation_id] = invocation.fingerprint
            self._in_flight.add(invocation.operation_id)

        try:
            result = handler.fn(isolated)
            result_json = _strict_json(result)
            result_bytes = result_json.encode("utf-8")
            if len(result_bytes) > self._result_limits[invocation.volume_id]:
                raise RuntimeError("result byte limit exceeded")
            result_digest = hashlib.sha256(result_bytes).hexdigest()
        except Exception as exc:
            failure = self._record_terminal_failure(
                invocation,
                handler=handler,
                ledger=ledger,
                exc=exc,
            )
            raise DeferredExecutionError(
                "deferred capability execution failed",
                failure,
            ) from exc
        except BaseException as exc:
            # The handler may already have produced an external effect before an
            # interpreter-level abort (KeyboardInterrupt/SystemExit/custom
            # BaseException). Reusing the operation id would therefore risk
            # duplicating an effect whose outcome is unknown. Preserve the
            # original abort for the caller, but fence the operation as a
            # terminal failure first.
            self._record_terminal_failure(
                invocation,
                handler=handler,
                ledger=ledger,
                exc=exc,
            )
            raise

        receipt = ExecutionReceipt(
            operation_id=invocation.operation_id,
            volume_id=invocation.volume_id,
            spec_digest=invocation.spec_digest,
            authority_digest=invocation.authority_digest,
            payload_digest=invocation.payload_digest,
            handler_identity=handler.identity,
            result_digest=result_digest,
            attempt=ledger.attempts,
            cost_units=ledger.cost_units,
            latency_ms=ledger.latency_ms,
        )
        with self._lock:
            self._success[invocation.operation_id] = receipt
            self._success_result_json[invocation.operation_id] = result_json
            self._in_flight.discard(invocation.operation_id)
        return ExecutionOutcome(
            receipt=receipt,
            result=json.loads(result_json),
        )

    def receipt(
        self,
        operation_id: str,
    ) -> ExecutionReceipt | FailureReceipt:
        operation_id = _text(operation_id, "operation_id")
        with self._lock:
            if operation_id in self._success:
                return self._success[operation_id]
            if operation_id in self._failure:
                return self._failure[operation_id]
        raise KeyError("unknown operation id")

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            operation_ids=sorted(set(self._success) | set(self._failure))
            receipts=[
                self._success.get(operation_id)
                or self._failure[operation_id]
                for operation_id in operation_ids
            ]
        rows=[
            {
                "receipt": receipt.as_dict(),
                "receipt_digest": receipt.digest,
            }
            for receipt in receipts
        ]
        payload = {
            "schema_version": 1,
            "operations": rows,
        }
        return {
            **payload,
            "snapshot_digest": sha256_json(payload),
        }

    @staticmethod
    def _receipt_fingerprint(
        receipt: ExecutionReceipt | FailureReceipt,
    ) -> str:
        return sha256_json(
            {
                "operation_id": receipt.operation_id,
                "volume_id": receipt.volume_id,
                "spec_digest": receipt.spec_digest,
                "authority_digest": receipt.authority_digest,
                "payload_digest": receipt.payload_digest,
                "cost_units": receipt.cost_units,
                "latency_ms": receipt.latency_ms,
            }
        )

    def export_state(self) -> dict[str, object]:
        """Export terminal operation state for exact restart recovery.

        In-flight operations are deliberately excluded: callers must only persist
        this state as a terminal replay checkpoint. The payload is content-bound
        at both receipt and whole-state levels.
        """
        with self._lock:
            operation_ids = sorted(set(self._success) | set(self._failure))
            rows: list[dict[str, object]] = []
            for operation_id in operation_ids:
                receipt = (
                    self._success.get(operation_id)
                    or self._failure[operation_id]
                )
                expected_fingerprint = self._receipt_fingerprint(receipt)
                fingerprint = self._fingerprints.get(operation_id)
                if fingerprint != expected_fingerprint:
                    raise RuntimeError(
                        "operation fingerprint state mismatch"
                    )
                row: dict[str, object] = {
                    "fingerprint": fingerprint,
                    "receipt": receipt.as_dict(),
                    "receipt_digest": receipt.digest,
                }
                if isinstance(receipt, ExecutionReceipt):
                    row["result"] = json.loads(
                        self._success_result_json[operation_id]
                    )
                rows.append(row)

        payload = {
            "schema_version": 1,
            "operations": rows,
        }
        return {
            **payload,
            "state_digest": sha256_json(payload),
        }

    def restore_state(self, state: Mapping[str, Any]) -> None:
        """Restore a verified terminal replay checkpoint into a fresh executor."""
        if not isinstance(state, Mapping):
            raise TypeError("state must be a mapping")

        state_dict = dict(state)
        if state_dict.get("schema_version") != 1:
            raise ValueError("unsupported deferred executor state schema")
        operations = state_dict.get("operations")
        if not isinstance(operations, list):
            raise TypeError("state operations must be a list")
        state_digest = _sha256(
            state_dict.get("state_digest"),
            "state_digest",
        )
        payload = {
            "schema_version": 1,
            "operations": operations,
        }
        if sha256_json(payload) != state_digest:
            raise ValueError("deferred executor state digest mismatch")

        restored_fingerprints: dict[str, str] = {}
        restored_success: dict[str, ExecutionReceipt] = {}
        restored_success_json: dict[str, str] = {}
        restored_failure: dict[str, FailureReceipt] = {}

        for raw_row in operations:
            if not isinstance(raw_row, Mapping):
                raise TypeError("state operation row must be a mapping")
            row = dict(raw_row)
            receipt_data = row.get("receipt")
            if not isinstance(receipt_data, Mapping):
                raise TypeError("state receipt must be a mapping")
            receipt_fields = dict(receipt_data)
            status = receipt_fields.get("status")
            if status == "succeeded":
                try:
                    receipt = ExecutionReceipt(**receipt_fields)
                except TypeError as exc:
                    raise ValueError("invalid success receipt fields") from exc
            elif status == "failed":
                try:
                    receipt = FailureReceipt(**receipt_fields)
                except TypeError as exc:
                    raise ValueError("invalid failure receipt fields") from exc
            else:
                raise ValueError("unsupported terminal receipt status")

            receipt_digest = _sha256(
                row.get("receipt_digest"),
                "receipt_digest",
            )
            if receipt.digest != receipt_digest:
                raise ValueError("terminal receipt digest mismatch")

            fingerprint = _sha256(
                row.get("fingerprint"),
                "fingerprint",
            )
            if fingerprint != self._receipt_fingerprint(receipt):
                raise ValueError("terminal operation fingerprint mismatch")

            if receipt.operation_id in restored_fingerprints:
                raise ValueError("duplicate terminal operation id")

            record = self.registry.get(receipt.volume_id)
            if record.spec.digest != receipt.spec_digest:
                raise ValueError("terminal receipt spec digest mismatch")
            if record.spec.handler != receipt.handler_identity:
                raise ValueError("terminal receipt handler identity mismatch")

            restored_fingerprints[receipt.operation_id] = fingerprint
            if isinstance(receipt, ExecutionReceipt):
                if "result" not in row:
                    raise ValueError("success checkpoint is missing result")
                result_json = _strict_json(row["result"])
                result_digest = hashlib.sha256(
                    result_json.encode("utf-8")
                ).hexdigest()
                if result_digest != receipt.result_digest:
                    raise ValueError("success checkpoint result digest mismatch")
                restored_success[receipt.operation_id] = receipt
                restored_success_json[receipt.operation_id] = result_json
            else:
                if "result" in row:
                    raise ValueError(
                        "failure checkpoint must not contain result"
                    )
                restored_failure[receipt.operation_id] = receipt

        with self._lock:
            if (
                self._fingerprints
                or self._in_flight
                or self._success
                or self._success_result_json
                or self._failure
            ):
                raise RuntimeError(
                    "restore_state requires a fresh executor"
                )
            self._fingerprints.update(restored_fingerprints)
            self._success.update(restored_success)
            self._success_result_json.update(restored_success_json)
            self._failure.update(restored_failure)

