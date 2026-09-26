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


class ToolAuthorityClass(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXTERNAL_COMMIT = "external_commit"
    PRIVILEGED = "privileged"


class ToolRiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolSideEffectClass(str, Enum):
    NONE = "none"
    LOCAL_REVERSIBLE = "local_reversible"
    LOCAL_IRREVERSIBLE = "local_irreversible"
    EXTERNAL_REVERSIBLE = "external_reversible"
    EXTERNAL_IRREVERSIBLE = "external_irreversible"


class ToolIdempotencyMode(str, Enum):
    NOT_REQUIRED = "not_required"
    INTRINSIC = "intrinsic"
    IDEMPOTENCY_KEY = "idempotency_key"
    RESERVATION_FENCE = "reservation_fence"
    COMPENSATABLE = "compensatable"


class ToolApprovalPolicy(str, Enum):
    NEVER = "never"
    POLICY = "policy"
    ALWAYS = "always"
    OPERATOR_ONLY = "operator_only"


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
    if field in {"input_schema", "output_schema"}:
        _validate_schema_shape(normalized)
    return normalized


_JSON_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})


def _validate_schema_shape(schema: Mapping[str, Any], *, depth: int = 0) -> None:
    if depth > 16:
        raise ToolContractError("input_schema exceeds maximum nesting depth")
    schema_type = schema.get("type")
    if schema_type is not None:
        if not isinstance(schema_type, str) or schema_type not in _JSON_TYPES:
            raise ToolContractError("input_schema type is invalid")
    properties = schema.get("properties")
    if properties is not None:
        if schema_type not in {None, "object"} or not isinstance(properties, Mapping):
            raise ToolContractError("input_schema properties require object schema")
        if len(properties) > 256:
            raise ToolContractError("input_schema has too many properties")
        for name, child in properties.items():
            if not isinstance(name, str) or not name:
                raise ToolContractError("input_schema property names must be non-empty strings")
            if not isinstance(child, Mapping):
                raise ToolContractError("input_schema property must be an object")
            _validate_schema_shape(child, depth=depth + 1)
    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required):
            raise ToolContractError("input_schema required must be a string list")
        if len(set(required)) != len(required):
            raise ToolContractError("input_schema required contains duplicates")
        if properties is not None and any(item not in properties for item in required):
            raise ToolContractError("input_schema required references unknown property")
    additional = schema.get("additionalProperties")
    if additional is not None and not isinstance(additional, (bool, Mapping)):
        raise ToolContractError("input_schema additionalProperties is invalid")
    if isinstance(additional, Mapping):
        _validate_schema_shape(additional, depth=depth + 1)
    items = schema.get("items")
    if items is not None:
        if schema_type not in {None, "array"} or not isinstance(items, Mapping):
            raise ToolContractError("input_schema items require array schema")
        _validate_schema_shape(items, depth=depth + 1)
    enum = schema.get("enum")
    if enum is not None:
        if not isinstance(enum, list) or not enum:
            raise ToolContractError("input_schema enum must be a non-empty list")
        try:
            json.dumps(enum, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ToolContractError("input_schema enum must be deterministic JSON") from exc
    for field in ("minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum"):
        if field not in schema:
            continue
        value = schema[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ToolContractError(f"input_schema {field} must be finite numeric")
        if field in {"minLength", "maxLength", "minItems", "maxItems"} and (
            not isinstance(value, int) or value < 0
        ):
            raise ToolContractError(f"input_schema {field} must be a non-negative integer")
    if (
        "minimum" in schema
        and "maximum" in schema
        and float(schema["minimum"]) > float(schema["maximum"])
    ):
        raise ToolContractError("input_schema minimum exceeds maximum")
    if (
        "minLength" in schema
        and "maxLength" in schema
        and int(schema["minLength"]) > int(schema["maxLength"])
    ):
        raise ToolContractError("input_schema minLength exceeds maxLength")
    if (
        "minItems" in schema
        and "maxItems" in schema
        and int(schema["minItems"]) > int(schema["maxItems"])
    ):
        raise ToolContractError("input_schema minItems exceeds maxItems")


def _matches_type(expected: str, value: object) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _validate_value(schema: Mapping[str, Any], value: object, *, path: str) -> None:
    expected = schema.get("type")
    if expected is not None and not _matches_type(str(expected), value):
        raise ToolContractError(f"{path} does not match schema type {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolContractError(f"{path} is outside schema enum")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ToolContractError(f"{path} is shorter than schema minimum")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ToolContractError(f"{path} exceeds schema maximum")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and float(value) < float(schema["minimum"]):
            raise ToolContractError(f"{path} is below schema minimum")
        if "maximum" in schema and float(value) > float(schema["maximum"]):
            raise ToolContractError(f"{path} exceeds schema maximum")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ToolContractError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ToolContractError(f"{path} has too many items")
        child = schema.get("items")
        if isinstance(child, Mapping):
            for index, item in enumerate(value):
                _validate_value(child, item, path=f"{path}[{index}]")
    if isinstance(value, Mapping):
        properties = schema.get("properties")
        properties = dict(properties) if isinstance(properties, Mapping) else {}
        required = schema.get("required") or []
        for name in required:
            if name not in value:
                raise ToolContractError(f"{path}.{name} is required")
        additional = schema.get("additionalProperties", True)
        for name, item in value.items():
            child = properties.get(name)
            if child is not None:
                _validate_value(child, item, path=f"{path}.{name}")
            elif additional is False:
                raise ToolContractError(f"{path}.{name} is not allowed")
            elif isinstance(additional, Mapping):
                _validate_value(additional, item, path=f"{path}.{name}")


def validate_tool_arguments(
    schema: Mapping[str, Any],
    arguments: Mapping[str, Any],
) -> None:
    """Validate runtime arguments against the supported canonical schema subset."""

    normalized_schema = _schema(schema, "input_schema")
    _validate_schema_shape(normalized_schema)
    if not isinstance(arguments, Mapping):
        raise ToolContractError("arguments must be an object")
    _validate_value(normalized_schema, dict(arguments), path="arguments")


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
    output_schema: Mapping[str, Any] | None = None
    capabilities: tuple[str, ...] = ()
    authority_class: ToolAuthorityClass = ToolAuthorityClass.READ
    risk_class: ToolRiskClass = ToolRiskClass.LOW
    side_effect_class: ToolSideEffectClass = ToolSideEffectClass.NONE
    idempotency_mode: ToolIdempotencyMode = ToolIdempotencyMode.NOT_REQUIRED
    approval_policy: ToolApprovalPolicy = ToolApprovalPolicy.NEVER
    network_policy: str = "none"
    data_policy: str = "internal"
    cost_model: Mapping[str, Any] | None = None
    result_size_limit: int = 1024 * 1024
    max_concurrency: int = 16
    enabled: bool = True
    effect: ToolEffect = ToolEffect.READ_ONLY
    approval_required: bool = False
    compensation_tool_id: str | None = None
    timeout_seconds: float = 30.0
    schema_version: int = TOOL_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_id", _tool_id(self.tool_id))
        _text(self.version, "version", max_length=64)
        _text(self.description, "description", max_length=2048)
        object.__setattr__(
            self,
            "input_schema",
            _schema(self.input_schema, "input_schema"),
        )
        output_schema = (
            {"type": "object"}
            if self.output_schema is None
            else self.output_schema
        )
        object.__setattr__(
            self,
            "output_schema",
            _schema(output_schema, "output_schema"),
        )

        normalized_capabilities: list[str] = []
        for raw in self.capabilities:
            capability = _text(raw, "capability", max_length=128)
            if capability not in normalized_capabilities:
                normalized_capabilities.append(capability)
        if len(normalized_capabilities) > 64:
            raise ToolContractError("capabilities exceeds maximum count")
        object.__setattr__(
            self,
            "capabilities",
            tuple(normalized_capabilities),
        )

        for field_name, enum_type in (
            ("authority_class", ToolAuthorityClass),
            ("risk_class", ToolRiskClass),
            ("side_effect_class", ToolSideEffectClass),
            ("idempotency_mode", ToolIdempotencyMode),
            ("approval_policy", ToolApprovalPolicy),
        ):
            try:
                value = enum_type(getattr(self, field_name))
            except ValueError as exc:
                raise ToolContractError(
                    f"{field_name} is invalid"
                ) from exc
            object.__setattr__(self, field_name, value)

        _text(self.network_policy, "network_policy", max_length=256)
        _text(self.data_policy, "data_policy", max_length=256)
        cost_model = (
            {"kind": "unmetered"}
            if self.cost_model is None
            else self.cost_model
        )
        normalized_cost_model = _schema(cost_model, "cost_model")
        if "estimated_cost_usd" in normalized_cost_model:
            raw_cost = normalized_cost_model["estimated_cost_usd"]
            if isinstance(raw_cost, bool) or not isinstance(
                raw_cost,
                (int, float),
            ):
                raise ToolContractError(
                    "cost_model.estimated_cost_usd must be non-negative numeric"
                )
            cost_value = float(raw_cost)
            if not math.isfinite(cost_value) or cost_value < 0:
                raise ToolContractError(
                    "cost_model.estimated_cost_usd must be non-negative numeric"
                )
        object.__setattr__(
            self,
            "cost_model",
            normalized_cost_model,
        )

        if (
            isinstance(self.result_size_limit, bool)
            or not isinstance(self.result_size_limit, int)
            or self.result_size_limit < 0
            or self.result_size_limit > 1024 * 1024 * 1024
        ):
            raise ToolContractError(
                "result_size_limit must be within [0, 1GiB]"
            )
        if (
            isinstance(self.max_concurrency, bool)
            or not isinstance(self.max_concurrency, int)
            or self.max_concurrency < 1
            or self.max_concurrency > 4096
        ):
            raise ToolContractError(
                "max_concurrency must be within [1, 4096]"
            )
        if not isinstance(self.enabled, bool):
            raise ToolContractError("enabled must be boolean")

        try:
            effect = ToolEffect(self.effect)
        except ValueError as exc:
            raise ToolContractError("effect is invalid") from exc
        object.__setattr__(self, "effect", effect)
        if not isinstance(self.approval_required, bool):
            raise ToolContractError("approval_required must be boolean")

        approval_policy = self.approval_policy
        if self.approval_required and approval_policy is ToolApprovalPolicy.NEVER:
            approval_policy = ToolApprovalPolicy.ALWAYS
            object.__setattr__(self, "approval_policy", approval_policy)
        if approval_policy in {
            ToolApprovalPolicy.ALWAYS,
            ToolApprovalPolicy.OPERATOR_ONLY,
        } and not self.approval_required:
            object.__setattr__(self, "approval_required", True)

        if effect is ToolEffect.IRREVERSIBLE and not self.approval_required:
            raise ToolContractError("irreversible tools require approval")
        if (
            self.risk_class is ToolRiskClass.CRITICAL
            and self.approval_policy is ToolApprovalPolicy.NEVER
        ):
            raise ToolContractError(
                "critical tools require non-never approval policy"
            )
        if (
            self.authority_class is not ToolAuthorityClass.READ
            and self.idempotency_mode is ToolIdempotencyMode.NOT_REQUIRED
        ):
            raise ToolContractError(
                "non-read authority requires an idempotency mode"
            )
        if (
            self.side_effect_class
            in {
                ToolSideEffectClass.EXTERNAL_IRREVERSIBLE,
                ToolSideEffectClass.LOCAL_IRREVERSIBLE,
            }
            and self.approval_policy is ToolApprovalPolicy.NEVER
        ):
            raise ToolContractError(
                "irreversible side effects require approval policy"
            )

        if self.compensation_tool_id is not None:
            object.__setattr__(
                self,
                "compensation_tool_id",
                _tool_id(self.compensation_tool_id),
            )
            if effect is ToolEffect.READ_ONLY:
                raise ToolContractError(
                    "read-only tools cannot declare compensation"
                )
        timeout = float(self.timeout_seconds)
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 3600:
            raise ToolContractError(
                "timeout_seconds must be within (0, 3600]"
            )
        object.__setattr__(self, "timeout_seconds", timeout)
        if self.schema_version != TOOL_CONTRACT_SCHEMA_VERSION:
            raise ToolContractError(
                "unsupported tool contract schema version"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_id": self.tool_id,
            "version": self.version,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema or {}),
            "capabilities": list(self.capabilities),
            "authority_class": self.authority_class.value,
            "risk_class": self.risk_class.value,
            "side_effect_class": self.side_effect_class.value,
            "idempotency_mode": self.idempotency_mode.value,
            "approval_policy": self.approval_policy.value,
            "network_policy": self.network_policy,
            "data_policy": self.data_policy,
            "cost_model": dict(self.cost_model or {}),
            "result_size_limit": self.result_size_limit,
            "max_concurrency": self.max_concurrency,
            "enabled": self.enabled,
            "effect": self.effect.value,
            "approval_required": self.approval_required,
            "compensation_tool_id": self.compensation_tool_id,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    request_id: str
    operation_id: str
    tenant_id: str
    tool_id: str
    idempotency_key: str
    arguments: Mapping[str, Any]
    requested_at: datetime
    execution_id: str | None = None
    turn_id: str | None = None
    call_id: str | None = None
    approval_ref: str | None = None
    delegated_authority_ref: str | None = None
    data_class: str = "internal"
    transfer_purpose: str = "tool-execution"
    schema_version: int = TOOL_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.request_id, "request_id")
        _uuid(self.operation_id, "operation_id")
        lineage = (self.execution_id, self.turn_id, self.call_id)
        if any(value is not None for value in lineage) and not all(
            value is not None for value in lineage
        ):
            raise ToolContractError(
                "execution_id, turn_id and call_id must be supplied together"
            )
        for field in ("execution_id", "turn_id", "call_id"):
            value = getattr(self, field)
            if value is not None:
                _text(value, field, max_length=512)
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
        data_class = _text(
            self.data_class,
            "data_class",
            max_length=64,
        ).lower()
        transfer_purpose = _text(
            self.transfer_purpose,
            "transfer_purpose",
            max_length=128,
        ).lower()
        object.__setattr__(self, "data_class", data_class)
        object.__setattr__(
            self,
            "transfer_purpose",
            transfer_purpose,
        )
        if self.schema_version != TOOL_CONTRACT_SCHEMA_VERSION:
            raise ToolContractError("unsupported tool contract schema version")

    @property
    def arguments_digest(self) -> str:
        return canonical_json_digest(self.arguments)


def approval_ref_for_request(request: ToolExecutionRequest) -> str:
    """Bind approval identity to the exact authority-relevant request shape."""

    if not isinstance(request, ToolExecutionRequest):
        raise TypeError("request must be ToolExecutionRequest")
    parts = [request.operation_id]
    if request.execution_id is not None:
        parts.extend(
            (request.execution_id, request.turn_id or "", request.call_id or "")
        )
    parts.extend((request.tenant_id, request.tool_id, request.arguments_digest))
    if (
        request.data_class != "internal"
        or request.transfer_purpose != "tool-execution"
    ):
        parts.extend((request.data_class, request.transfer_purpose))
    material = "\x1f".join(parts).encode("utf-8")
    return "approval:" + hashlib.sha256(material).hexdigest()


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
    execution_id: str | None = None
    turn_id: str | None = None
    call_id: str | None = None
    result_ref: str | None = None
    error_code: str | None = None
    approval_ref: str | None = None
    compensation_ref: str | None = None
    data_class: str = "internal"
    transfer_purpose: str = "tool-execution"
    governance_decision_ref: str | None = None
    metered_tool_calls: int = 1
    schema_version: int = TOOL_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.receipt_id, "receipt_id")
        _uuid(self.request_id, "request_id")
        _uuid(self.operation_id, "operation_id")
        lineage = (self.execution_id, self.turn_id, self.call_id)
        if any(value is not None for value in lineage) and not all(
            value is not None for value in lineage
        ):
            raise ToolContractError(
                "execution_id, turn_id and call_id must be supplied together"
            )
        for field in ("execution_id", "turn_id", "call_id"):
            value = getattr(self, field)
            if value is not None:
                _text(value, field, max_length=512)
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
        object.__setattr__(
            self,
            "data_class",
            _text(self.data_class, "data_class", max_length=64).lower(),
        )
        object.__setattr__(
            self,
            "transfer_purpose",
            _text(
                self.transfer_purpose,
                "transfer_purpose",
                max_length=128,
            ).lower(),
        )
        if self.governance_decision_ref is not None:
            _text(
                self.governance_decision_ref,
                "governance_decision_ref",
                max_length=256,
            )
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
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "call_id": self.call_id,
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
            "data_class": self.data_class,
            "transfer_purpose": self.transfer_purpose,
            "governance_decision_ref": self.governance_decision_ref,
            "metered_tool_calls": self.metered_tool_calls,
        }


__all__ = [
    "TOOL_CONTRACT_SCHEMA_VERSION",
    "ToolApprovalPolicy",
    "ToolAuthorityClass",
    "ToolContractError",
    "ToolEffect",
    "ToolIdempotencyMode",
    "ToolRiskClass",
    "ToolSideEffectClass",
    "ToolExecutionRequest",
    "ToolExecutionReceipt",
    "ToolExecutionStatus",
    "ToolManifest",
    "approval_ref_for_request",
    "canonical_json_digest",
    "validate_tool_arguments",
]
