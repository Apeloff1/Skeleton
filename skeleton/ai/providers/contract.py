"""Shared mandatory architecture acknowledgement for AI provider families.

This module is intentionally dependency-light and performs no provider/network
I/O. Every credential-bearing AI provider family must obtain a receipt here
before it can perform external model I/O.

The receipt proves that:
* the active architecture and AI-construction contracts are materialized;
* every mandatory provider document was read into the digest;
* the provider is declared in the correct provider family;
* architecture/manual acknowledgement and activation receipts are required.

Provider families keep runtime model providers, automation model providers, and
other future external AI edges under one contract without making backend code
the owner of repository-wide policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any


class ProviderArchitectureError(RuntimeError):
    """Provider activation cannot satisfy the mandatory architecture contract."""


@dataclass(frozen=True, slots=True)
class ProviderArchitectureReceipt:
    """Non-secret evidence that a provider loaded the active construction contract."""

    provider_id: str
    architecture_tag: str
    construction_version: str
    contract_digest: str
    manual_path: str
    required_documents: tuple[str, ...]
    provider_family: str = "runtime_model"

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "architecture_tag": self.architecture_tag,
            "construction_version": self.construction_version,
            "contract_digest": self.contract_digest,
            "manual_path": self.manual_path,
            "required_documents": list(self.required_documents),
        }


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProviderArchitectureError(
            f"mandatory provider contract is unavailable: {path}"
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderArchitectureError(
            f"mandatory provider contract is invalid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderArchitectureError(
            f"mandatory provider contract must be an object: {path}"
        )
    return payload, raw


def _candidate_roots(explicit: str | Path | None) -> list[Path]:
    roots: list[Path] = []
    if explicit is not None:
        roots.append(Path(explicit))
    configured = os.getenv("AI_ARCHITECTURE_ROOT", "").strip()
    if configured:
        roots.append(Path(configured))
    roots.append(Path.cwd())

    here = Path(__file__).resolve()
    roots.extend(here.parents)

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in roots:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def locate_contract_root(explicit: str | Path | None = None) -> Path:
    """Find the materialized construction root without consulting the network.

    An explicit root is authoritative: if it is incomplete, activation fails
    closed instead of silently falling back to another checkout.
    """

    if explicit is not None:
        root = Path(explicit).resolve()
        if (
            (root / "machine/manifest.json").is_file()
            and (root / "machine/architecture.json").is_file()
            and (root / "machine/ai_app_construction.json").is_file()
            and (root / "docs/AI_APP_CONSTRUCTION_MANUAL.md").is_file()
        ):
            return root
        raise ProviderArchitectureError(
            "mandatory AI architecture contracts are not materialized at explicit root"
        )

    for root in _candidate_roots(None):
        if (
            (root / "machine/manifest.json").is_file()
            and (root / "machine/architecture.json").is_file()
            and (root / "machine/ai_app_construction.json").is_file()
            and (root / "docs/AI_APP_CONSTRUCTION_MANUAL.md").is_file()
        ):
            return root
    raise ProviderArchitectureError(
        "mandatory AI architecture contracts are not materialized; "
        "set AI_ARCHITECTURE_ROOT or package machine/ and docs/ with the runtime"
    )


def _provider_list_name(provider_family: str) -> str:
    normalized = provider_family.strip().lower().replace("-", "_")
    mapping = {
        "runtime_model": "runtime_model_providers",
        "automation_model": "automation_model_providers",
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise ProviderArchitectureError(
            f"unknown provider family: {provider_family!r}"
        ) from exc


def load_provider_architecture(
    provider_id: str,
    *,
    provider_family: str = "runtime_model",
    root: str | Path | None = None,
) -> ProviderArchitectureReceipt:
    """Load and validate mandatory construction documents for one provider."""

    normalized = str(provider_id).strip().lower()
    family = str(provider_family).strip().lower().replace("-", "_")
    if not normalized:
        raise ProviderArchitectureError(
            "provider id is required for architecture acknowledgement"
        )

    contract_root = locate_contract_root(root)
    architecture, architecture_raw = _read_json(
        contract_root / "machine/architecture.json"
    )
    construction, construction_raw = _read_json(
        contract_root / "machine/ai_app_construction.json"
    )

    if architecture.get("status") != "active":
        raise ProviderArchitectureError("architecture contract is not active")
    if construction.get("status") != "active":
        raise ProviderArchitectureError("AI construction contract is not active")

    architecture_tag = architecture.get("architecture_tag")
    if not isinstance(architecture_tag, str) or not architecture_tag:
        raise ProviderArchitectureError("architecture tag is missing")
    if construction.get("architecture_tag") != architecture_tag:
        raise ProviderArchitectureError(
            "AI construction contract architecture tag does not match active architecture"
        )

    bootstrap = construction.get("provider_bootstrap")
    if not isinstance(bootstrap, dict):
        raise ProviderArchitectureError("provider bootstrap contract is missing")
    if bootstrap.get("mandatory") is not True or bootstrap.get("mode") != "fail_closed":
        raise ProviderArchitectureError(
            "provider bootstrap must be mandatory and fail-closed"
        )

    required_documents = bootstrap.get("must_read")
    if not isinstance(required_documents, list) or not required_documents:
        raise ProviderArchitectureError(
            "provider bootstrap must declare required documents"
        )

    digest = hashlib.sha256()
    digest.update(architecture_raw)
    digest.update(construction_raw)
    normalized_documents: list[str] = []
    for relative in required_documents:
        if not isinstance(relative, str) or not relative:
            raise ProviderArchitectureError(
                "provider bootstrap contains an invalid document path"
            )
        path = contract_root / relative
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ProviderArchitectureError(
                f"mandatory provider document is unavailable: {relative}"
            ) from exc
        if not raw.strip():
            raise ProviderArchitectureError(
                f"mandatory provider document is empty: {relative}"
            )
        digest.update(relative.encode("utf-8"))
        digest.update(raw)
        normalized_documents.append(relative)

    declaration_key = _provider_list_name(family)
    declared = construction.get(declaration_key)
    if not isinstance(declared, list):
        raise ProviderArchitectureError(f"{declaration_key} must be a list")
    declaration = next(
        (
            item
            for item in declared
            if isinstance(item, dict)
            and str(item.get("id", "")).strip().lower() == normalized
        ),
        None,
    )
    if declaration is None:
        raise ProviderArchitectureError(
            f"AI provider is not declared in {declaration_key}: {normalized}"
        )
    for key in (
        "architecture_read_required",
        "construction_manual_read_required",
        "activation_receipt_required",
    ):
        if declaration.get(key) is not True:
            raise ProviderArchitectureError(
                f"provider {normalized} does not require {key}"
            )

    construction_version = construction.get("construction_version")
    if not isinstance(construction_version, str) or not construction_version:
        raise ProviderArchitectureError("construction version is missing")

    manual_path = construction.get("human_manual")
    if not isinstance(manual_path, str) or not manual_path:
        raise ProviderArchitectureError("construction human manual path is missing")
    if manual_path not in normalized_documents:
        raise ProviderArchitectureError(
            "construction manual must be included in mandatory provider documents"
        )

    return ProviderArchitectureReceipt(
        provider_id=normalized,
        provider_family=family,
        architecture_tag=architecture_tag,
        construction_version=construction_version,
        contract_digest=digest.hexdigest(),
        manual_path=manual_path,
        required_documents=tuple(normalized_documents),
    )




PROVIDER_PROTOCOL_SCHEMA_VERSION = 1
_PROVIDER_TOOL_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_DIGEST256 = re.compile(r"^[0-9a-f]{64}$")


class ProviderProtocolError(ValueError):
    """Provider-neutral interaction contract is malformed."""


class FinishReason(str, Enum):
    COMPLETED = "completed"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    CONTENT_FILTERED = "content_filtered"
    REFUSAL = "refusal"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN = "unknown"


class ProviderDeltaKind(str, Enum):
    TEXT = "text"
    STRUCTURED = "structured"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    FINAL = "final"


def _protocol_text(
    value: object,
    field_name: str,
    *,
    max_length: int,
    optional: bool = False,
) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ProviderProtocolError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized and not optional:
        raise ProviderProtocolError(f"{field_name} must be non-empty")
    if normalized != value:
        raise ProviderProtocolError(f"{field_name} must be normalized")
    if len(normalized) > max_length:
        raise ProviderProtocolError(f"{field_name} exceeds maximum length")
    return normalized


def _protocol_json_object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderProtocolError(f"{field_name} must be an object")
    result = dict(value)
    try:
        encoded = json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProviderProtocolError(
            f"{field_name} must be deterministic JSON"
        ) from exc
    if len(encoded.encode("utf-8")) > 512 * 1024:
        raise ProviderProtocolError(f"{field_name} exceeds maximum size")
    return result


def provider_arguments_digest(arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        _protocol_json_object(arguments, "arguments"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _non_negative_int_or_none(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderProtocolError(
            f"{field_name} must be a non-negative integer or null"
        )
    return value


def _decimal_string_or_none(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProviderProtocolError(f"{field_name} must be decimal text or null")
    raw = str(value).strip()
    if not raw:
        raise ProviderProtocolError(f"{field_name} must be decimal text or null")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ProviderProtocolError(f"{field_name} must be decimal text") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ProviderProtocolError(
            f"{field_name} must be a finite non-negative decimal"
        )
    return raw


@dataclass(frozen=True, slots=True)
class ProviderToolDefinition:
    tool_id: str
    description: str
    input_schema: dict[str, Any]
    schema_version: int = PROVIDER_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        tool_id = _protocol_text(self.tool_id, "tool_id", max_length=128)
        assert tool_id is not None
        if _PROVIDER_TOOL_ID.fullmatch(tool_id) is None:
            raise ProviderProtocolError("tool_id is invalid")
        object.__setattr__(self, "tool_id", tool_id)
        _protocol_text(self.description, "description", max_length=4096)
        object.__setattr__(
            self,
            "input_schema",
            _protocol_json_object(self.input_schema, "input_schema"),
        )
        if self.schema_version != PROVIDER_PROTOCOL_SCHEMA_VERSION:
            raise ProviderProtocolError("unsupported provider protocol schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "description": self.description,
            "input_schema": dict(self.input_schema),
        }

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.tool_id,
            "description": self.description,
            "parameters": dict(self.input_schema),
            "strict": True,
        }


@dataclass(frozen=True, slots=True)
class ProviderToolCall:
    call_id: str
    tool_id: str
    arguments: dict[str, Any]
    arguments_digest: str | None = None
    schema_version: int = PROVIDER_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        call_id = _protocol_text(self.call_id, "call_id", max_length=256)
        tool_id = _protocol_text(self.tool_id, "tool_id", max_length=128)
        assert call_id is not None and tool_id is not None
        if _PROVIDER_TOOL_ID.fullmatch(tool_id) is None:
            raise ProviderProtocolError("tool_id is invalid")
        args = _protocol_json_object(self.arguments, "arguments")
        digest = provider_arguments_digest(args)
        if self.arguments_digest is not None and self.arguments_digest != digest:
            raise ProviderProtocolError("arguments_digest does not match arguments")
        object.__setattr__(self, "call_id", call_id)
        object.__setattr__(self, "tool_id", tool_id)
        object.__setattr__(self, "arguments", args)
        object.__setattr__(self, "arguments_digest", digest)
        if self.schema_version != PROVIDER_PROTOCOL_SCHEMA_VERSION:
            raise ProviderProtocolError("unsupported provider protocol schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_id": self.tool_id,
            "arguments": dict(self.arguments),
            "arguments_digest": self.arguments_digest,
        }


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: str | None = None
    billed_cost: str | None = None
    currency: str | None = None
    usage_source: str = "unknown"
    schema_version: int = PROVIDER_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "total_tokens",
        ):
            object.__setattr__(
                self,
                name,
                _non_negative_int_or_none(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "estimated_cost",
            _decimal_string_or_none(self.estimated_cost, "estimated_cost"),
        )
        object.__setattr__(
            self,
            "billed_cost",
            _decimal_string_or_none(self.billed_cost, "billed_cost"),
        )
        if self.currency is not None:
            currency = _protocol_text(
                self.currency,
                "currency",
                max_length=16,
                optional=True,
            )
            assert currency is not None
            object.__setattr__(self, "currency", currency.upper())
        source = _protocol_text(
            self.usage_source,
            "usage_source",
            max_length=64,
        )
        assert source is not None
        object.__setattr__(self, "usage_source", source)
        if (
            self.total_tokens is not None
            and self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens < self.input_tokens + self.output_tokens
        ):
            raise ProviderProtocolError(
                "total_tokens cannot be less than input_tokens + output_tokens"
            )
        if self.schema_version != PROVIDER_PROTOCOL_SCHEMA_VERSION:
            raise ProviderProtocolError("unsupported provider protocol schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "billed_cost": self.billed_cost,
            "currency": self.currency,
            "usage_source": self.usage_source,
        }


@dataclass(frozen=True, slots=True)
class ProviderStructuredOutput:
    schema: dict[str, Any]
    value: dict[str, Any] | None = None
    schema_version: int = PROVIDER_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema",
            _protocol_json_object(self.schema, "structured_output.schema"),
        )
        if self.value is not None:
            object.__setattr__(
                self,
                "value",
                _protocol_json_object(self.value, "structured_output.value"),
            )
        if self.schema_version != PROVIDER_PROTOCOL_SCHEMA_VERSION:
            raise ProviderProtocolError("unsupported provider protocol schema version")


@dataclass(frozen=True, slots=True)
class ProviderDelta:
    sequence: int
    kind: ProviderDeltaKind
    response_id: str | None = None
    text: str | None = None
    structured_fragment: dict[str, Any] | None = None
    tool_call: ProviderToolCall | None = None
    usage: ProviderUsage | None = None
    finish_reason: FinishReason | None = None
    emitted_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    schema_version: int = PROVIDER_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ProviderProtocolError("delta sequence must be a non-negative integer")
        try:
            kind = ProviderDeltaKind(self.kind)
        except ValueError as exc:
            raise ProviderProtocolError("delta kind is invalid") from exc
        object.__setattr__(self, "kind", kind)
        if self.response_id is not None:
            _protocol_text(
                self.response_id,
                "response_id",
                max_length=256,
                optional=True,
            )
        if self.text is not None and not isinstance(self.text, str):
            raise ProviderProtocolError("delta text must be text")
        if self.structured_fragment is not None:
            object.__setattr__(
                self,
                "structured_fragment",
                _protocol_json_object(
                    self.structured_fragment,
                    "structured_fragment",
                ),
            )
        if self.tool_call is not None and not isinstance(
            self.tool_call, ProviderToolCall
        ):
            raise ProviderProtocolError("delta tool_call must be ProviderToolCall")
        if self.usage is not None and not isinstance(self.usage, ProviderUsage):
            raise ProviderProtocolError("delta usage must be ProviderUsage")
        if self.finish_reason is not None:
            try:
                object.__setattr__(
                    self,
                    "finish_reason",
                    FinishReason(self.finish_reason),
                )
            except ValueError as exc:
                raise ProviderProtocolError("finish_reason is invalid") from exc
        if (
            not isinstance(self.emitted_at, datetime)
            or self.emitted_at.tzinfo is None
            or self.emitted_at.utcoffset() is None
        ):
            raise ProviderProtocolError("emitted_at must be timezone-aware")
        object.__setattr__(
            self,
            "emitted_at",
            self.emitted_at.astimezone(timezone.utc),
        )
        payload_count = sum(
            (
                self.text is not None,
                self.structured_fragment is not None,
                self.tool_call is not None,
                self.usage is not None,
                self.finish_reason is not None,
            )
        )
        if kind is not ProviderDeltaKind.FINAL and payload_count != 1:
            raise ProviderProtocolError(
                "non-final delta must carry exactly one payload"
            )
        if kind is ProviderDeltaKind.TEXT and self.text is None:
            raise ProviderProtocolError("text delta requires text")
        if (
            kind is ProviderDeltaKind.STRUCTURED
            and self.structured_fragment is None
        ):
            raise ProviderProtocolError(
                "structured delta requires structured_fragment"
            )
        if kind is ProviderDeltaKind.TOOL_CALL and self.tool_call is None:
            raise ProviderProtocolError("tool_call delta requires tool_call")
        if kind is ProviderDeltaKind.USAGE and self.usage is None:
            raise ProviderProtocolError("usage delta requires usage")
        if kind is ProviderDeltaKind.FINAL and self.finish_reason is None:
            raise ProviderProtocolError("final delta requires finish_reason")
        if self.schema_version != PROVIDER_PROTOCOL_SCHEMA_VERSION:
            raise ProviderProtocolError("unsupported provider protocol schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "response_id": self.response_id,
            "text": self.text,
            "structured_fragment": self.structured_fragment,
            "tool_call": (
                None if self.tool_call is None else self.tool_call.as_dict()
            ),
            "usage": None if self.usage is None else self.usage.as_dict(),
            "finish_reason": (
                None if self.finish_reason is None else self.finish_reason.value
            ),
            "emitted_at": self.emitted_at.isoformat(),
        }


__all__ = [
    "FinishReason",
    "PROVIDER_PROTOCOL_SCHEMA_VERSION",
    "ProviderArchitectureError",
    "ProviderArchitectureReceipt",
    "ProviderDelta",
    "ProviderDeltaKind",
    "ProviderProtocolError",
    "ProviderStructuredOutput",
    "ProviderToolCall",
    "ProviderToolDefinition",
    "ProviderUsage",
    "provider_arguments_digest",
    "load_provider_architecture",
    "locate_contract_root",
]
