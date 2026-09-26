"""Canonical deterministic tool registry and execution runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import threading
from typing import Awaitable, Callable, Protocol
from uuid import uuid4

from skeleton.intelligence.admission import UsageEstimate
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.skills.tool_contract import (
    ToolContractError,
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionReceipt,
    ToolExecutionStatus,
    ToolManifest,
    approval_ref_for_request,
    validate_tool_arguments,
)
from skeleton.skills.tool_receipt_store import (
    SQLiteToolReceiptStore,
    ToolReceiptConflict,
)
from skeleton.vault.data_governance import (
    DataGovernanceDenied,
    ToolTransferRequest,
    evaluate_tool_transfer,
)


class ToolRuntimeError(RuntimeError):
    """Base tool runtime failure."""


class ToolNotFound(ToolRuntimeError):
    """Requested tool is not registered."""


class ToolExecutionConflict(ToolRuntimeError):
    """Idempotency identity was replayed with different inputs."""


class ToolExecutionDenied(ToolRuntimeError):
    """Deterministic authority checks denied the request."""


class ToolHandler(Protocol):
    def __call__(self, request: ToolExecutionRequest) -> str | None:
        """Execute a tool and return a durable result reference when applicable."""


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    manifest: ToolManifest
    handler: ToolHandler


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ToolRuntimeError("timestamps must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _estimated_tool_cost_usd(manifest: ToolManifest) -> float:
    raw = (manifest.cost_model or {}).get("estimated_cost_usd", 0.0)
    if isinstance(raw, bool):
        raise ToolRuntimeError("estimated_cost_usd must be non-negative numeric")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ToolRuntimeError(
            "estimated_cost_usd must be non-negative numeric"
        ) from exc
    if value < 0 or value == float("inf") or value != value:
        raise ToolRuntimeError("estimated_cost_usd must be non-negative numeric")
    return value


def _meter_manifest_usage(
    admission_runtime,
    request: ToolExecutionRequest,
    manifest: ToolManifest,
    *,
    started: datetime,
) -> None:
    event_id = f"tool:{request.request_id}"
    cost_usd = _estimated_tool_cost_usd(manifest)
    record_usage = getattr(admission_runtime, "record_usage_event", None)
    if callable(record_usage):
        record_usage(
            request.operation_id,
            event_id,
            "tool",
            UsageEstimate(tool_calls=1, cost_usd=cost_usd),
            now_wall=started.timestamp(),
        )
        return
    admission_runtime.meter_tool_call(
        request.operation_id,
        event_id,
        now_wall=started.timestamp(),
    )


def _tool_governance_decision(
    manifest: ToolManifest,
    request: ToolExecutionRequest,
):
    return evaluate_tool_transfer(
        ToolTransferRequest(
            tool_id=manifest.tool_id,
            data_policy=manifest.data_policy,
            network_policy=manifest.network_policy,
            data_class=request.data_class,
            purpose=request.transfer_purpose,
            tenant_id=request.tenant_id,
            source="canonical-tool-runtime",
        )
    )


def _receipt_id(request: ToolExecutionRequest, manifest: ToolManifest) -> str:
    parts = [request.operation_id]
    if request.execution_id is not None:
        parts.extend(
            (request.execution_id, request.turn_id or "", request.call_id or "")
        )
    parts.extend(
        (
            request.tenant_id,
            request.tool_id,
            manifest.version,
            request.idempotency_key,
            request.arguments_digest,
        )
    )
    if (
        request.data_class != "internal"
        or request.transfer_purpose != "tool-execution"
    ):
        parts.extend((request.data_class, request.transfer_purpose))
    material = "\x1f".join(parts).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    # Receipt remains canonical UUID-shaped while deterministically derived.
    return str(
        uuid4()
    ) if not digest else (
        f"{digest[0:8]}-{digest[8:12]}-4{digest[13:16]}-"
        f"8{digest[17:20]}-{digest[20:32]}"
    )


class ToolRuntime:
    """Thread-safe registry and fail-closed execution boundary.

    The runtime deliberately stores only receipts, not arbitrary tool outputs.
    Tool handlers must persist large or sensitive results behind a result_ref.
    """

    def __init__(
        self,
        *,
        admission_runtime: AdmissionRuntime | None = None,
        receipt_store: SQLiteToolReceiptStore | None = None,
    ) -> None:
        self.admission_runtime = admission_runtime
        self.receipt_store = receipt_store
        self._lock = threading.RLock()
        self._registry: dict[str, RegisteredTool] = {}
        self._receipts: dict[tuple[str, str, str], ToolExecutionReceipt] = {}
        self._request_fingerprints: dict[
            tuple[str, str, str],
            tuple[
                str,
                str,
                str | None,
                str | None,
                str | None,
                str,
                str,
            ],
        ] = {}

    def register(self, manifest: ToolManifest, handler: ToolHandler) -> ToolManifest:
        if not isinstance(manifest, ToolManifest):
            raise TypeError("manifest must be ToolManifest")
        if not callable(handler):
            raise TypeError("handler must be callable")
        with self._lock:
            existing = self._registry.get(manifest.tool_id)
            if existing is not None and existing.manifest != manifest:
                raise ToolExecutionConflict("tool_id already registered with different manifest")
            self._registry[manifest.tool_id] = RegisteredTool(manifest, handler)
        return manifest

    def manifest(self, tool_id: str) -> ToolManifest:
        with self._lock:
            item = self._registry.get(str(tool_id))
            if item is None:
                raise ToolNotFound("tool is not registered")
            return item.manifest

    def manifests(self) -> tuple[ToolManifest, ...]:
        with self._lock:
            return tuple(
                self._registry[key].manifest
                for key in sorted(self._registry)
            )

    def receipt(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> ToolExecutionReceipt | None:
        key = (tenant_id, operation_id, idempotency_key)
        with self._lock:
            cached = self._receipts.get(key)
            if cached is not None:
                return cached
            if self.receipt_store is None:
                return None
            durable = self.receipt_store.get(
                tenant_id=tenant_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )
            if durable is None or durable.status != "committed":
                return None
            assert durable.receipt is not None
            self._receipts[key] = durable.receipt
            self._request_fingerprints[key] = (
                durable.receipt.tool_id,
                durable.receipt.arguments_digest,
                durable.receipt.execution_id,
                durable.receipt.turn_id,
                durable.receipt.call_id,
                durable.receipt.data_class,
                durable.receipt.transfer_purpose,
            )
            return durable.receipt

    def execute(
        self,
        request: ToolExecutionRequest,
        *,
        now: datetime | None = None,
    ) -> ToolExecutionReceipt:
        if not isinstance(request, ToolExecutionRequest):
            raise TypeError("request must be ToolExecutionRequest")
        started = _utc(now)
        key = (request.tenant_id, request.operation_id, request.idempotency_key)
        governance_decision_ref: str | None = None

        with self._lock:
            registered = self._registry.get(request.tool_id)
            if registered is None:
                raise ToolNotFound("tool is not registered")

            fingerprint = (
                request.tool_id,
                request.arguments_digest,
                request.execution_id,
                request.turn_id,
                request.call_id,
                request.data_class,
                request.transfer_purpose,
            )
            previous_fingerprint = self._request_fingerprints.get(key)
            if previous_fingerprint is not None and previous_fingerprint != fingerprint:
                raise ToolExecutionConflict(
                    "idempotency_key replayed with different tool or arguments or lineage"
                )
            existing = self._receipts.get(key)
            if existing is not None:
                return existing

            manifest = registered.manifest
            try:
                validate_tool_arguments(manifest.input_schema, request.arguments)
            except ToolContractError:
                receipt = ToolExecutionReceipt(
                    receipt_id=_receipt_id(request, manifest),
                    request_id=request.request_id,
                    operation_id=request.operation_id,
                    execution_id=request.execution_id,
                    turn_id=request.turn_id,
                    call_id=request.call_id,
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.DENIED,
                    started_at=started,
                    finished_at=started,
                    error_code="arguments_invalid",
                    approval_ref=request.approval_ref,
                    data_class=request.data_class,
                    transfer_purpose=request.transfer_purpose,
                    governance_decision_ref=governance_decision_ref,
                    metered_tool_calls=0,
                )
                self._request_fingerprints[key] = fingerprint
                self._receipts[key] = receipt
                return receipt

            try:
                governance = _tool_governance_decision(
                    manifest,
                    request,
                )
            except DataGovernanceDenied:
                governance = None
            if governance is None or not governance.permitted:
                error_code = (
                    "governance_denied"
                    if governance is None
                    else governance.reason_code
                )
                governance_decision_ref = (
                    None if governance is None else governance.decision_id
                )
                receipt = ToolExecutionReceipt(
                    receipt_id=_receipt_id(request, manifest),
                    request_id=request.request_id,
                    operation_id=request.operation_id,
                    execution_id=request.execution_id,
                    turn_id=request.turn_id,
                    call_id=request.call_id,
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.DENIED,
                    started_at=started,
                    finished_at=started,
                    error_code=error_code,
                    approval_ref=request.approval_ref,                    data_class=request.data_class,
                    transfer_purpose=request.transfer_purpose,
                    governance_decision_ref=governance_decision_ref,
                    metered_tool_calls=0,
                )
                self._request_fingerprints[key] = fingerprint
                self._receipts[key] = receipt
                return receipt
            governance_decision_ref = governance.decision_id

            if manifest.approval_required:
                expected_approval = approval_ref_for_request(request)
                if request.approval_ref is None:
                    # Missing approval is a resumable wait state. Do not persist it
                    # under the idempotency key or an approved resume would replay
                    # this denial forever.
                    return ToolExecutionReceipt(
                        receipt_id=_receipt_id(request, manifest),
                        request_id=request.request_id,
                        operation_id=request.operation_id,
                        execution_id=request.execution_id,
                        turn_id=request.turn_id,
                        call_id=request.call_id,
                        tenant_id=request.tenant_id,
                        tool_id=request.tool_id,
                        idempotency_key=request.idempotency_key,
                        arguments_digest=request.arguments_digest,
                        status=ToolExecutionStatus.DENIED,
                        started_at=started,
                        finished_at=started,
                        error_code="approval_required",
                        approval_ref=None,
                        data_class=request.data_class,
                        transfer_purpose=request.transfer_purpose,
                        governance_decision_ref=governance_decision_ref,
                        metered_tool_calls=0,
                    )
                if request.approval_ref != expected_approval:
                    return ToolExecutionReceipt(
                        receipt_id=_receipt_id(request, manifest),
                        request_id=request.request_id,
                        operation_id=request.operation_id,
                        execution_id=request.execution_id,
                        turn_id=request.turn_id,
                        call_id=request.call_id,
                        tenant_id=request.tenant_id,
                        tool_id=request.tool_id,
                        idempotency_key=request.idempotency_key,
                        arguments_digest=request.arguments_digest,
                        status=ToolExecutionStatus.DENIED,
                        started_at=started,
                        finished_at=started,
                        error_code="approval_binding_mismatch",
                        approval_ref=request.approval_ref,
                        data_class=request.data_class,
                        transfer_purpose=request.transfer_purpose,
                        governance_decision_ref=governance_decision_ref,
                        metered_tool_calls=0,
                    )

            if self.receipt_store is not None:
                try:
                    reservation = self.receipt_store.reserve(
                        request,
                        now=started,
                    )
                except ToolReceiptConflict as exc:
                    raise ToolExecutionConflict(str(exc)) from exc
                if reservation.status == "committed":
                    assert reservation.receipt is not None
                    self._request_fingerprints[key] = fingerprint
                    self._receipts[key] = reservation.receipt
                    return reservation.receipt
                if reservation.status == "in_doubt":
                    return ToolExecutionReceipt(
                        receipt_id=_receipt_id(request, manifest),
                        request_id=request.request_id,
                        operation_id=request.operation_id,
                        execution_id=request.execution_id,
                        turn_id=request.turn_id,
                        call_id=request.call_id,
                        tenant_id=request.tenant_id,
                        tool_id=request.tool_id,
                        idempotency_key=request.idempotency_key,
                        arguments_digest=request.arguments_digest,
                        status=ToolExecutionStatus.DENIED,
                        started_at=started,
                        finished_at=started,
                        error_code="execution_in_doubt",
                        approval_ref=request.approval_ref,
                        data_class=request.data_class,
                        transfer_purpose=request.transfer_purpose,
                        governance_decision_ref=governance_decision_ref,
                        metered_tool_calls=0,
                    )

            self._request_fingerprints[key] = fingerprint

            # Meter before invoking any side effect. AdmissionRuntime is expected
            # to have an active operation lease when budget enforcement is used.
            if self.admission_runtime is not None:
                try:
                    _meter_manifest_usage(
                        self.admission_runtime,
                        request,
                        manifest,
                        started=started,
                    )
                except Exception:
                    receipt = ToolExecutionReceipt(
                        receipt_id=_receipt_id(request, manifest),
                        request_id=request.request_id,
                        operation_id=request.operation_id,
                        execution_id=request.execution_id,
                        turn_id=request.turn_id,
                        call_id=request.call_id,
                        tenant_id=request.tenant_id,
                        tool_id=request.tool_id,
                        idempotency_key=request.idempotency_key,
                        arguments_digest=request.arguments_digest,
                        status=ToolExecutionStatus.DENIED,
                        started_at=started,
                        finished_at=_utc(),
                        error_code="budget_denied",
                        approval_ref=request.approval_ref,
                        data_class=request.data_class,
                        transfer_purpose=request.transfer_purpose,
                        governance_decision_ref=governance_decision_ref,
                        metered_tool_calls=0,
                    )
                    if self.receipt_store is not None:
                        receipt = self.receipt_store.commit(
                            request,
                            receipt,
                            now=started,
                        )
                    self._receipts[key] = receipt
                    return receipt

            try:
                result_ref = registered.handler(request)
                if result_ref is not None:
                    result_ref = str(result_ref).strip()
                    if not result_ref:
                        raise ToolRuntimeError("tool returned an empty result_ref")
                finished = _utc()
                receipt = ToolExecutionReceipt(
                    receipt_id=_receipt_id(request, manifest),
                    request_id=request.request_id,
                    operation_id=request.operation_id,
                    execution_id=request.execution_id,
                    turn_id=request.turn_id,
                    call_id=request.call_id,
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.SUCCEEDED,
                    started_at=started,
                    finished_at=max(started, finished),
                    result_ref=result_ref,
                    approval_ref=request.approval_ref,
                    data_class=request.data_class,
                    transfer_purpose=request.transfer_purpose,
                    governance_decision_ref=governance_decision_ref,
                    metered_tool_calls=1,
                )
            except Exception as exc:
                finished = _utc()
                receipt = ToolExecutionReceipt(
                    receipt_id=_receipt_id(request, manifest),
                    request_id=request.request_id,
                    operation_id=request.operation_id,
                    execution_id=request.execution_id,
                    turn_id=request.turn_id,
                    call_id=request.call_id,
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.FAILED,
                    started_at=started,
                    finished_at=max(started, finished),
                    error_code=type(exc).__name__,
                    approval_ref=request.approval_ref,
                    data_class=request.data_class,
                    transfer_purpose=request.transfer_purpose,
                    governance_decision_ref=governance_decision_ref,
                    metered_tool_calls=1,
                )
            if self.receipt_store is not None:
                receipt = self.receipt_store.commit(
                    request,
                    receipt,
                )
            self._receipts[key] = receipt
            return receipt




class AsyncToolHandler(Protocol):
    async def __call__(self, request: ToolExecutionRequest) -> str | None:
        """Execute one async tool call and return a durable result reference."""


AsyncPostcondition = Callable[[ToolExecutionRequest, str | None], bool | Awaitable[bool]]
AsyncCompensator = Callable[[ToolExecutionRequest, str | None], str | None | Awaitable[str | None]]


@dataclass(frozen=True, slots=True)
class RegisteredAsyncTool:
    manifest: ToolManifest
    handler: AsyncToolHandler
    postcondition: AsyncPostcondition | None = None
    compensate: AsyncCompensator | None = None


async def _await_maybe(value):
    if hasattr(value, "__await__"):
        return await value
    return value


class AsyncToolRuntime:
    """Concurrent canonical runtime with idempotency reservation fencing.

    A key is reserved before the handler starts. Concurrent exact retries await
    the same future instead of executing the side effect again. Conflicting
    retries fail immediately. Optional postconditions may trigger a compensator
    before a failed receipt is published.
    """

    def __init__(
        self,
        *,
        admission_runtime: AdmissionRuntime | None = None,
        receipt_store: SQLiteToolReceiptStore | None = None,
    ) -> None:
        self.admission_runtime = admission_runtime
        self.receipt_store = receipt_store
        self._lock = asyncio.Lock()
        self._registry: dict[str, RegisteredAsyncTool] = {}
        self._receipts: dict[tuple[str, str, str], ToolExecutionReceipt] = {}
        self._request_fingerprints: dict[
            tuple[str, str, str],
            tuple[str, str, str | None, str | None, str | None],
        ] = {}
        self._inflight: dict[
            tuple[str, str, str], asyncio.Future[ToolExecutionReceipt]
        ] = {}
        self._tool_semaphores: dict[str, asyncio.Semaphore] = {}

    async def register(
        self,
        manifest: ToolManifest,
        handler: AsyncToolHandler,
        *,
        postcondition: AsyncPostcondition | None = None,
        compensate: AsyncCompensator | None = None,
    ) -> ToolManifest:
        if not isinstance(manifest, ToolManifest):
            raise TypeError("manifest must be ToolManifest")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if postcondition is not None and not callable(postcondition):
            raise TypeError("postcondition must be callable")
        if compensate is not None and not callable(compensate):
            raise TypeError("compensate must be callable")
        if compensate is not None and manifest.effect is ToolEffect.READ_ONLY:
            raise ToolExecutionDenied("read-only tools cannot register compensation")
        async with self._lock:
            existing = self._registry.get(manifest.tool_id)
            candidate = RegisteredAsyncTool(
                manifest=manifest,
                handler=handler,
                postcondition=postcondition,
                compensate=compensate,
            )
            if existing is not None and existing.manifest != manifest:
                raise ToolExecutionConflict(
                    "tool_id already registered with different manifest"
                )
            self._registry[manifest.tool_id] = candidate
            if manifest.tool_id not in self._tool_semaphores:
                self._tool_semaphores[manifest.tool_id] = asyncio.Semaphore(
                    manifest.max_concurrency
                )
        return manifest

    async def manifest(self, tool_id: str) -> ToolManifest:
        async with self._lock:
            item = self._registry.get(str(tool_id))
            if item is None:
                raise ToolNotFound("tool is not registered")
            return item.manifest

    async def manifests(self) -> tuple[ToolManifest, ...]:
        async with self._lock:
            return tuple(
                self._registry[key].manifest for key in sorted(self._registry)
            )

    async def receipt(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> ToolExecutionReceipt | None:
        key = (tenant_id, operation_id, idempotency_key)
        async with self._lock:
            cached = self._receipts.get(key)
            if cached is not None:
                return cached
            if self.receipt_store is None:
                return None
            durable = self.receipt_store.get(
                tenant_id=tenant_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )
            if durable is None or durable.status != "committed":
                return None
            assert durable.receipt is not None
            self._receipts[key] = durable.receipt
            self._request_fingerprints[key] = (
                durable.receipt.tool_id,
                durable.receipt.arguments_digest,
                durable.receipt.execution_id,
                durable.receipt.turn_id,
                durable.receipt.call_id,
            )
            return durable.receipt

    async def execute(
        self,
        request: ToolExecutionRequest,
        *,
        now: datetime | None = None,
    ) -> ToolExecutionReceipt:
        if not isinstance(request, ToolExecutionRequest):
            raise TypeError("request must be ToolExecutionRequest")
        started = _utc(now)
        key = (request.tenant_id, request.operation_id, request.idempotency_key)
        fingerprint = (
            request.tool_id,
            request.arguments_digest,
            request.execution_id,
            request.turn_id,
            request.call_id,
        )
        owner = False
        governance_decision_ref: str | None = None

        async with self._lock:
            registered = self._registry.get(request.tool_id)
            if registered is None:
                raise ToolNotFound("tool is not registered")

            previous = self._request_fingerprints.get(key)
            if previous is not None and previous != fingerprint:
                raise ToolExecutionConflict(
                    "idempotency_key replayed with different tool or arguments or lineage"
                )
            existing = self._receipts.get(key)
            if existing is not None:
                return existing

            inflight = self._inflight.get(key)
            if inflight is not None:
                waiter = inflight
            else:
                try:
                    validate_tool_arguments(
                        registered.manifest.input_schema,
                        request.arguments,
                    )
                except ToolContractError:
                    receipt = ToolExecutionReceipt(
                        receipt_id=_receipt_id(request, registered.manifest),
                        request_id=request.request_id,
                        operation_id=request.operation_id,
                        execution_id=request.execution_id,
                        turn_id=request.turn_id,
                        call_id=request.call_id,
                        tenant_id=request.tenant_id,
                        tool_id=request.tool_id,
                        idempotency_key=request.idempotency_key,
                        arguments_digest=request.arguments_digest,
                        status=ToolExecutionStatus.DENIED,
                        started_at=started,
                        finished_at=started,
                        error_code="arguments_invalid",
                        approval_ref=request.approval_ref,
                        data_class=request.data_class,
                        transfer_purpose=request.transfer_purpose,
                        governance_decision_ref=governance_decision_ref,
                        metered_tool_calls=0,
                    )
                    self._request_fingerprints[key] = fingerprint
                    self._receipts[key] = receipt
                    return receipt

                try:
                    governance = _tool_governance_decision(
                        registered.manifest,
                        request,
                    )
                except DataGovernanceDenied:
                    governance = None
                if governance is None or not governance.permitted:
                    error_code = (
                        "governance_denied"
                        if governance is None
                        else governance.reason_code
                    )
                    governance_decision_ref = (
                        None
                        if governance is None
                        else governance.decision_id
                    )
                    receipt = ToolExecutionReceipt(
                        receipt_id=_receipt_id(
                            request,
                            registered.manifest,
                        ),
                        request_id=request.request_id,
                        operation_id=request.operation_id,
                        execution_id=request.execution_id,
                        turn_id=request.turn_id,
                        call_id=request.call_id,
                        tenant_id=request.tenant_id,
                        tool_id=request.tool_id,
                        idempotency_key=request.idempotency_key,
                        arguments_digest=request.arguments_digest,
                        status=ToolExecutionStatus.DENIED,
                        started_at=started,
                        finished_at=started,
                        error_code=error_code,
                        approval_ref=request.approval_ref,                        data_class=request.data_class,
                        transfer_purpose=request.transfer_purpose,
                        governance_decision_ref=governance_decision_ref,
                        metered_tool_calls=0,
                    )
                    self._request_fingerprints[key] = fingerprint
                    self._receipts[key] = receipt
                    return receipt
                governance_decision_ref = governance.decision_id

                if registered.manifest.approval_required:
                    expected_approval = approval_ref_for_request(request)
                    if request.approval_ref is None:
                        # Missing approval is a resumable wait state. It is returned
                        # to orchestration but intentionally not published as the
                        # idempotent terminal receipt for this call.
                        return ToolExecutionReceipt(
                            receipt_id=_receipt_id(request, registered.manifest),
                            request_id=request.request_id,
                            operation_id=request.operation_id,
                            execution_id=request.execution_id,
                            turn_id=request.turn_id,
                            call_id=request.call_id,
                            tenant_id=request.tenant_id,
                            tool_id=request.tool_id,
                            idempotency_key=request.idempotency_key,
                            arguments_digest=request.arguments_digest,
                            status=ToolExecutionStatus.DENIED,
                            started_at=started,
                            finished_at=started,
                            error_code="approval_required",
                            approval_ref=None,
                            data_class=request.data_class,
                            transfer_purpose=request.transfer_purpose,
                            governance_decision_ref=governance_decision_ref,
                            metered_tool_calls=0,
                        )
                    if request.approval_ref != expected_approval:
                        return ToolExecutionReceipt(
                            receipt_id=_receipt_id(request, registered.manifest),
                            request_id=request.request_id,
                            operation_id=request.operation_id,
                            execution_id=request.execution_id,
                            turn_id=request.turn_id,
                            call_id=request.call_id,
                            tenant_id=request.tenant_id,
                            tool_id=request.tool_id,
                            idempotency_key=request.idempotency_key,
                            arguments_digest=request.arguments_digest,
                            status=ToolExecutionStatus.DENIED,
                            started_at=started,
                            finished_at=started,
                            error_code="approval_binding_mismatch",
                            approval_ref=request.approval_ref,
                            data_class=request.data_class,
                            transfer_purpose=request.transfer_purpose,
                            governance_decision_ref=governance_decision_ref,
                            metered_tool_calls=0,
                        )

                if self.receipt_store is not None:
                    try:
                        reservation = self.receipt_store.reserve(
                            request,
                            now=started,
                        )
                    except ToolReceiptConflict as exc:
                        raise ToolExecutionConflict(str(exc)) from exc
                    if reservation.status == "committed":
                        assert reservation.receipt is not None
                        self._request_fingerprints[key] = fingerprint
                        self._receipts[key] = reservation.receipt
                        return reservation.receipt
                    if reservation.status == "in_doubt":
                        return ToolExecutionReceipt(
                            receipt_id=_receipt_id(request, registered.manifest),
                            request_id=request.request_id,
                            operation_id=request.operation_id,
                            execution_id=request.execution_id,
                            turn_id=request.turn_id,
                            call_id=request.call_id,
                            tenant_id=request.tenant_id,
                            tool_id=request.tool_id,
                            idempotency_key=request.idempotency_key,
                            arguments_digest=request.arguments_digest,
                            status=ToolExecutionStatus.DENIED,
                            started_at=started,
                            finished_at=started,
                            error_code="execution_in_doubt",
                            approval_ref=request.approval_ref,
                            data_class=request.data_class,
                            transfer_purpose=request.transfer_purpose,
                            governance_decision_ref=governance_decision_ref,
                            metered_tool_calls=0,
                        )

                self._request_fingerprints[key] = fingerprint
                waiter = asyncio.get_running_loop().create_future()
                self._inflight[key] = waiter
                owner = True

        if not owner:
            return await asyncio.shield(waiter)

        receipt: ToolExecutionReceipt
        try:
            if self.admission_runtime is not None:
                try:
                    _meter_manifest_usage(
                        self.admission_runtime,
                        request,
                        registered.manifest,
                        started=started,
                    )
                except Exception:
                    receipt = ToolExecutionReceipt(
                        receipt_id=_receipt_id(request, registered.manifest),
                        request_id=request.request_id,
                        operation_id=request.operation_id,
                        execution_id=request.execution_id,
                        turn_id=request.turn_id,
                        call_id=request.call_id,
                        tenant_id=request.tenant_id,
                        tool_id=request.tool_id,
                        idempotency_key=request.idempotency_key,
                        arguments_digest=request.arguments_digest,
                        status=ToolExecutionStatus.DENIED,
                        started_at=started,
                        finished_at=_utc(),
                        error_code="budget_denied",
                        approval_ref=request.approval_ref,
                        data_class=request.data_class,
                        transfer_purpose=request.transfer_purpose,
                        governance_decision_ref=governance_decision_ref,
                        metered_tool_calls=0,
                    )
                else:
                    semaphore = self._tool_semaphores[request.tool_id]
                    async with semaphore:
                        receipt = await self._execute_registered(
                            registered,
                            request,
                            started=started,
                            governance_decision_ref=governance_decision_ref,
                        )
            else:
                semaphore = self._tool_semaphores[request.tool_id]
                async with semaphore:
                    receipt = await self._execute_registered(
                        registered,
                        request,
                        started=started,
                        governance_decision_ref=governance_decision_ref,
                    )
            if self.receipt_store is not None:
                receipt = self.receipt_store.commit(
                    request,
                    receipt,
                )
        except BaseException as exc:
            async with self._lock:
                pending = self._inflight.pop(key, None)
                self._request_fingerprints.pop(key, None)
                if pending is not None and not pending.done():
                    if isinstance(exc, asyncio.CancelledError):
                        pending.cancel()
                    else:
                        pending.set_exception(exc)
            raise

        async with self._lock:
            self._receipts[key] = receipt
            pending = self._inflight.pop(key, None)
            if pending is not None and not pending.done():
                pending.set_result(receipt)
        return receipt

    async def _execute_registered(
        self,
        registered: RegisteredAsyncTool,
        request: ToolExecutionRequest,
        *,
        started: datetime,
        governance_decision_ref: str | None,
    ) -> ToolExecutionReceipt:
        manifest = registered.manifest
        try:
            result_ref = await registered.handler(request)
            if result_ref is not None:
                result_ref = str(result_ref).strip()
                if not result_ref:
                    raise ToolRuntimeError("tool returned an empty result_ref")

            postcondition_ok = True
            if registered.postcondition is not None:
                postcondition_ok = bool(
                    await _await_maybe(
                        registered.postcondition(request, result_ref)
                    )
                )
            if not postcondition_ok:
                compensation_ref: str | None = None
                if registered.compensate is not None:
                    compensation_ref = await _await_maybe(
                        registered.compensate(request, result_ref)
                    )
                    if compensation_ref is not None:
                        compensation_ref = str(compensation_ref).strip()
                        if not compensation_ref:
                            raise ToolRuntimeError(
                                "compensator returned an empty reference"
                            )
                return ToolExecutionReceipt(
                    receipt_id=_receipt_id(request, manifest),
                    request_id=request.request_id,
                    operation_id=request.operation_id,
                    execution_id=request.execution_id,
                    turn_id=request.turn_id,
                    call_id=request.call_id,
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.FAILED,
                    started_at=started,
                    finished_at=max(started, _utc()),
                    error_code="postcondition_failed",
                    approval_ref=request.approval_ref,
                    compensation_ref=compensation_ref,
                    data_class=request.data_class,
                    transfer_purpose=request.transfer_purpose,
                    governance_decision_ref=governance_decision_ref,
                    metered_tool_calls=1,
                )

            return ToolExecutionReceipt(
                receipt_id=_receipt_id(request, manifest),
                request_id=request.request_id,
                operation_id=request.operation_id,
                execution_id=request.execution_id,
                turn_id=request.turn_id,
                call_id=request.call_id,
                tenant_id=request.tenant_id,
                tool_id=request.tool_id,
                idempotency_key=request.idempotency_key,
                arguments_digest=request.arguments_digest,
                status=ToolExecutionStatus.SUCCEEDED,
                started_at=started,
                finished_at=max(started, _utc()),
                result_ref=result_ref,
                approval_ref=request.approval_ref,
                data_class=request.data_class,
                transfer_purpose=request.transfer_purpose,
                governance_decision_ref=governance_decision_ref,
                metered_tool_calls=1,
            )
        except Exception as exc:
            return ToolExecutionReceipt(
                receipt_id=_receipt_id(request, manifest),
                request_id=request.request_id,
                operation_id=request.operation_id,
                execution_id=request.execution_id,
                turn_id=request.turn_id,
                call_id=request.call_id,
                tenant_id=request.tenant_id,
                tool_id=request.tool_id,
                idempotency_key=request.idempotency_key,
                arguments_digest=request.arguments_digest,
                status=ToolExecutionStatus.FAILED,
                started_at=started,
                finished_at=max(started, _utc()),
                error_code=type(exc).__name__,
                approval_ref=request.approval_ref,
                data_class=request.data_class,
                transfer_purpose=request.transfer_purpose,
                governance_decision_ref=governance_decision_ref,
                metered_tool_calls=1,
            )


__all__ = [
    "AsyncCompensator",
    "AsyncPostcondition",
    "AsyncToolHandler",
    "AsyncToolRuntime",
    "RegisteredAsyncTool",
    "RegisteredTool",
    "ToolExecutionConflict",
    "ToolExecutionDenied",
    "ToolHandler",
    "ToolNotFound",
    "ToolRuntime",
    "ToolRuntimeError",
]
