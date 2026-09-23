"""Canonical deterministic tool registry and execution runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import threading
from typing import Callable, Protocol
from uuid import uuid4

from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.skills.tool_contract import (
    ToolContractError,
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionReceipt,
    ToolExecutionStatus,
    ToolManifest,
    validate_tool_arguments,
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


def _receipt_id(request: ToolExecutionRequest, manifest: ToolManifest) -> str:
    material = "\x1f".join(
        (
            request.operation_id,
            request.tenant_id,
            request.tool_id,
            manifest.version,
            request.idempotency_key,
            request.arguments_digest,
        )
    ).encode("utf-8")
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

    def __init__(self, *, admission_runtime: AdmissionRuntime | None = None) -> None:
        self.admission_runtime = admission_runtime
        self._lock = threading.RLock()
        self._registry: dict[str, RegisteredTool] = {}
        self._receipts: dict[tuple[str, str, str], ToolExecutionReceipt] = {}
        self._request_fingerprints: dict[tuple[str, str, str], tuple[str, str]] = {}

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
        with self._lock:
            return self._receipts.get((tenant_id, operation_id, idempotency_key))

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

        with self._lock:
            registered = self._registry.get(request.tool_id)
            if registered is None:
                raise ToolNotFound("tool is not registered")

            fingerprint = (request.tool_id, request.arguments_digest)
            previous_fingerprint = self._request_fingerprints.get(key)
            if previous_fingerprint is not None and previous_fingerprint != fingerprint:
                raise ToolExecutionConflict(
                    "idempotency_key replayed with different tool or arguments"
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
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.DENIED,
                    started_at=started,
                    finished_at=started,
                    error_code="arguments_invalid",
                    approval_ref=request.approval_ref,
                    metered_tool_calls=0,
                )
                self._request_fingerprints[key] = fingerprint
                self._receipts[key] = receipt
                return receipt

            self._request_fingerprints[key] = fingerprint

            if manifest.approval_required and request.approval_ref is None:
                receipt = ToolExecutionReceipt(
                    receipt_id=_receipt_id(request, manifest),
                    request_id=request.request_id,
                    operation_id=request.operation_id,
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.DENIED,
                    started_at=started,
                    finished_at=started,
                    error_code="approval_required",
                    approval_ref=None,
                    metered_tool_calls=0,
                )
                self._receipts[key] = receipt
                return receipt

            # Meter before invoking any side effect. AdmissionRuntime is expected
            # to have an active operation lease when budget enforcement is used.
            if self.admission_runtime is not None:
                self.admission_runtime.meter_tool_call(
                    request.operation_id,
                    f"tool:{request.request_id}",
                    now_wall=started.timestamp(),
                )

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
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.SUCCEEDED,
                    started_at=started,
                    finished_at=max(started, finished),
                    result_ref=result_ref,
                    approval_ref=request.approval_ref,
                    metered_tool_calls=1,
                )
            except Exception as exc:
                finished = _utc()
                receipt = ToolExecutionReceipt(
                    receipt_id=_receipt_id(request, manifest),
                    request_id=request.request_id,
                    operation_id=request.operation_id,
                    tenant_id=request.tenant_id,
                    tool_id=request.tool_id,
                    idempotency_key=request.idempotency_key,
                    arguments_digest=request.arguments_digest,
                    status=ToolExecutionStatus.FAILED,
                    started_at=started,
                    finished_at=max(started, finished),
                    error_code=type(exc).__name__,
                    approval_ref=request.approval_ref,
                    metered_tool_calls=1,
                )
            self._receipts[key] = receipt
            return receipt


__all__ = [
    "RegisteredTool",
    "ToolExecutionConflict",
    "ToolExecutionDenied",
    "ToolHandler",
    "ToolNotFound",
    "ToolRuntime",
    "ToolRuntimeError",
]
