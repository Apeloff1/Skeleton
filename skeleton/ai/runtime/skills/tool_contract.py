"""Canonical provider-neutral tool execution contracts.

Tool execution is a privileged side-effect boundary. Model output may propose a
request, but only deterministic policy/runtime code may authorize execution.
Receipts are durable lineage objects and never contain raw secrets by design.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping
from uuid import UUID


TOOL_CONTRACT_SCHEMA_VERSION = 1
_TOOL_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class ToolContractError(ValueError):
    """A canonical tool contract is malformed."""


class ToolEffect(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class ToolExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"


def _text(value: object, field: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolContractError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise ToolContractError(f"{field} must be normalized")
    if len(normalized) > max_length:
        raise ToolContractError(f"{field} exceeds maximum length")
    return normalized


def _uuid(value: object, field: str) -> str:
    raw = _text(value, field, max_length=64)
    try:
        parsed = UUID(raw)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ToolContractError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != raw:
        raise ToolContractError(f"{field} must be a canonical UUID")
    return raw


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ToolContractError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _tool_id(value: object) -> str:
    raw = _text(value, "tool_id", max_length=128)
    if not _TOOL_ID.fullmatch(raw):
        raise ToolContractError("tool_id is invalid")
    return raw


def _schema(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ToolContractError(f"{field} must be a mapping")
    normalized = dict(value)
    try:
        json.dumps(normalized, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ToolContractError(f"{field} must be deterministic JSON") from exc
    return normalized


def canonical_json_digest(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ToolContractError("arguments must be deterministic JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ToolManifest:
    tool_id: str
    version: str
    description: str
    input_schema: Mapping[str, Any]
    effect: ToolEffect = ToolEffect.READ_ONLY
    approval_required: bool = False
    compensation_tool_id: str | None = None
    timeout_seconds: float = 30.0
    schema_version: int = TOOL_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_id", _tool_id(self.tool_id))
        _text(self.version, "version", max_length=64)
        _text(self.description, "description", max_length=2048)
        object.__setattr__(self, "input_schema", _schema(self.input_schema, "input_schema"))
        try:
            effect = ToolEffect(self.effect)
        except ValueError as exc:
            raise ToolContractError("effect is invalid") from exc
        object.__setattr__(self, "effect", effect)
        if not isinstance(self.approval_required, bool):
            raise ToolContractError("approval_required must be boolean")
        if effect is ToolEffect.IRREVERSIBLE and not self.approval_required:
            raise ToolContractError("irreversible tools require approval")
        if self.compensation_tool_id is not None:
            object.__setattr__(self, "compensation_tool_id", _tool_id(self.compensation_tool_id))
            if effect is ToolEffect.READ_ONLY:
                raise ToolContractError("read-only tools cannot declare compensation")
        timeout = float(self.timeout_seconds)
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 3600:
            raise ToolContractError("timeout_seconds must be within (0, 3600]")
        object.__setattr__(self, "timeout_seconds", timeout)
        if self.schema_version != TOOL_CONTRACT_SCHEMA_VERSION:
            raise ToolContractError("unsupported tool contract schema version")


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    request_id: str
    operation_id: str
    tenant_id: str
    tool_id: str
    idempotency_key: str
    arguments: Mapping[str, Any]
    requested_at: datetime
    approval_ref: str | None = None
    delegated_authority_ref: str | None = None
    schema_version: int = TOOL_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.request_id, "request_id")
        _uuid(self.operation_id, "operation_id")
        _text(self.tenant_id, "tenant_id")
        object.__setattr__(self, "tool_id", _tool_id(self.tool_id))
        _text(self.idempotency_key, "idempotency_key", max_length=1024)
        object.__setattr__(self, "arguments", _schema(self.arguments, "arguments"))
        _utc(self.requested_at, "requested_at")
        if self.approval_ref is not None:
            _text(self.approval_ref, "approval_ref", max_length=1024)
        if self.delegated_authority_ref is not None:
            _text(
                self.delegated_authority_ref,
                "delegated_authority_ref",
                max_length=1024,
            )
        if self.schema_version != TOOL_CONTRACT_SCHEMA_VERSION:
            raise ToolContractError("unsupported tool contract schema version")

    @property
    def arguments_digest(self) -> str:
        return canonical_json_digest(self.arguments)


@dataclass(frozen=True, slots=True)
class ToolExecutionReceipt:
    receipt_id: str
    request_id: str
    operation_id: str
    tenant_id: str
    tool_id: str
    idempotency_key: str
    arguments_digest: str
    status: ToolExecutionStatus
    started_at: datetime
    finished_at: datetime
    result_ref: str | None = None
    error_code: str | None = None
    approval_ref: str | None = None
    compensation_ref: str | None = None
    metered_tool_calls: int = 1
    schema_version: int = TOOL_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.receipt_id, "receipt_id")
        _uuid(self.request_id, "request_id")
        _uuid(self.operation_id, "operation_id")
        _text(self.tenant_id, "tenant_id")
        object.__setattr__(self, "tool_id", _tool_id(self.tool_id))
        _text(self.idempotency_key, "idempotency_key", max_length=1024)
        digest = _text(self.arguments_digest, "arguments_digest", max_length=64)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ToolContractError("arguments_digest must be lowercase sha256")
        try:
            status = ToolExecutionStatus(self.status)
        except ValueError as exc:
            raise ToolContractError("status is invalid") from exc
        object.__setattr__(self, "status", status)
        started = _utc(self.started_at, "started_at")
        finished = _utc(self.finished_at, "finished_at")
        if finished < started:
            raise ToolContractError("finished_at must not precede started_at")
        if self.result_ref is not None:
            _text(self.result_ref, "result_ref", max_length=2048)
        if self.error_code is not None:
            _text(self.error_code, "error_code", max_length=256)
        if status is ToolExecutionStatus.SUCCEEDED and self.error_code is not None:
            raise ToolContractError("successful receipt cannot carry error_code")
        if status is not ToolExecutionStatus.SUCCEEDED and self.result_ref is not None:
            raise ToolContractError("non-success receipt cannot carry result_ref")
        if self.approval_ref is not None:
            _text(self.approval_ref, "approval_ref", max_length=1024)
        if self.compensation_ref is not None:
            _text(self.compensation_ref, "compensation_ref", max_length=1024)
        if (
            isinstance(self.metered_tool_calls, bool)
            or not isinstance(self.metered_tool_calls, int)
            or self.metered_tool_calls < 0
        ):
            raise ToolContractError("metered_tool_calls must be a non-negative integer")
        if self.schema_version != TOOL_CONTRACT_SCHEMA_VERSION:
            raise ToolContractError("unsupported tool contract schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "request_id": self.request_id,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "tool_id": self.tool_id,
            "idempotency_key": self.idempotency_key,
            "arguments_digest": self.arguments_digest,
            "status": self.status.value,
            "started_at": self.started_at.astimezone(timezone.utc).isoformat(),
            "finished_at": self.finished_at.astimezone(timezone.utc).isoformat(),
            "result_ref": self.result_ref,
            "error_code": self.error_code,
            "approval_ref": self.approval_ref,
            "compensation_ref": self.compensation_ref,
            "metered_tool_calls": self.metered_tool_calls,
        }


__all__ = [
    "TOOL_CONTRACT_SCHEMA_VERSION",
    "ToolContractError",
    "ToolEffect",
    "ToolExecutionRequest",
    "ToolExecutionReceipt",
    "ToolExecutionStatus",
    "ToolManifest",
    "canonical_json_digest",
]
