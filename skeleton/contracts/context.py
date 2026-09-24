"""Canonical provider-neutral prompt-context contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterable
from uuid import UUID


CONTEXT_SCHEMA_VERSION = 1


class ContextContractError(ValueError):
    """A context contract violates canonical invariants."""


class ContextKind(str, Enum):
    SYSTEM_POLICY = "system_policy"
    PRODUCT_INSTRUCTION = "product_instruction"
    OPERATION_OBJECTIVE = "operation_objective"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    CONVERSATION_SUMMARY = "conversation_summary"
    MEMORY = "memory"
    RETRIEVAL_EVIDENCE = "retrieval_evidence"
    ARTIFACT = "artifact"
    TOOL_RESULT = "tool_result"
    SKILL_INSTRUCTION = "skill_instruction"
    TOOL_SCHEMA = "tool_schema"


class ContextTrust(str, Enum):
    TRUSTED_CONTROL = "trusted_control"
    AUTHORIZED_USER_DATA = "authorized_user_data"
    UNTRUSTED_EVIDENCE = "untrusted_evidence"
    DERIVED_UNTRUSTED = "derived_untrusted"


_DATA_CLASSES = ("public", "internal", "confidential", "restricted")


def _text(value: object, field: str, *, max_length: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextContractError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise ContextContractError(f"{field} must be normalized")
    if len(normalized) > max_length:
        raise ContextContractError(f"{field} exceeds maximum length")
    return normalized


def _uuid(value: object, field: str) -> str:
    raw = _text(value, field, max_length=64)
    try:
        parsed = UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise ContextContractError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != raw:
        raise ContextContractError(f"{field} must be a canonical UUID")
    return raw


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise ContextContractError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContextContractError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContextContractError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result == 0:
        raise ContextContractError(f"{field} must be positive")
    return result


def _data_class(value: object) -> str:
    normalized = _text(value, "data_class", max_length=32).lower()
    if normalized not in _DATA_CLASSES:
        raise ContextContractError("data_class is invalid")
    return normalized


def _digest_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def estimate_tokens(content: str) -> int:
    """Conservative tokenizer-neutral estimate used before provider projection."""
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    if not content:
        return 0
    # UTF-8 bytes / 3 intentionally overestimates typical English tokenization.
    return max(1, math.ceil(len(content.encode("utf-8")) / 3))


def _refs(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ContextContractError(f"{field} must be an iterable")
    result: list[str] = []
    for raw in values:
        value = _text(raw, field, max_length=1024)
        if value not in result:
            result.append(value)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_context_tokens: int
    reserved_output_tokens: int
    reserved_tool_result_tokens: int
    reserved_policy_tokens: int
    safety_margin_tokens: int
    max_segment_tokens: int
    max_artifact_tokens: int
    max_tool_result_tokens: int

    def __post_init__(self) -> None:
        for field in (
            "max_context_tokens",
            "reserved_output_tokens",
            "reserved_tool_result_tokens",
            "reserved_policy_tokens",
            "safety_margin_tokens",
            "max_segment_tokens",
            "max_artifact_tokens",
            "max_tool_result_tokens",
        ):
            value = getattr(self, field)
            if field in {"max_context_tokens", "max_segment_tokens"}:
                _positive_int(value, field)
            else:
                _nonnegative_int(value, field)
        if self.reserved_output_tokens + self.safety_margin_tokens >= self.max_context_tokens:
            raise ContextContractError(
                "output reserve plus safety margin exhausts context budget"
            )
        if self.reserved_policy_tokens > self.input_capacity(tools_enabled=False):
            raise ContextContractError("reserved_policy_tokens exceeds input capacity")

    def input_capacity(self, *, tools_enabled: bool) -> int:
        reserve = self.reserved_output_tokens + self.safety_margin_tokens
        if tools_enabled:
            reserve += self.reserved_tool_result_tokens
        return max(0, self.max_context_tokens - reserve)

    def as_dict(self) -> dict[str, int]:
        return {
            "max_context_tokens": self.max_context_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "reserved_tool_result_tokens": self.reserved_tool_result_tokens,
            "reserved_policy_tokens": self.reserved_policy_tokens,
            "safety_margin_tokens": self.safety_margin_tokens,
            "max_segment_tokens": self.max_segment_tokens,
            "max_artifact_tokens": self.max_artifact_tokens,
            "max_tool_result_tokens": self.max_tool_result_tokens,
        }


@dataclass(frozen=True, slots=True)
class ContextSegment:
    segment_id: str
    kind: ContextKind
    source_type: str
    source_id: str
    content_ref: str
    content_digest: str
    trust_level: ContextTrust
    data_class: str
    tenant_id: str
    purpose: str
    priority: int
    relevance: float
    created_at: datetime
    token_estimate: int
    provenance: tuple[str, ...]
    retention_class: str
    content: str | None = None
    derived_from: tuple[str, ...] = ()
    mandatory: bool = False
    schema_version: int = CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.segment_id, "segment_id")
        try:
            kind = ContextKind(self.kind)
        except ValueError as exc:
            raise ContextContractError("kind is invalid") from exc
        try:
            trust = ContextTrust(self.trust_level)
        except ValueError as exc:
            raise ContextContractError("trust_level is invalid") from exc
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "trust_level", trust)
        _text(self.source_type, "source_type", max_length=128)
        _text(self.source_id, "source_id", max_length=1024)
        _text(self.content_ref, "content_ref", max_length=2048)
        digest = _text(self.content_digest, "content_digest", max_length=64)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ContextContractError("content_digest must be lowercase sha256 hex")
        object.__setattr__(self, "data_class", _data_class(self.data_class))
        _text(self.tenant_id, "tenant_id")
        _text(self.purpose, "purpose", max_length=256)
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ContextContractError("priority must be an integer")
        if self.priority < -1000 or self.priority > 1000:
            raise ContextContractError("priority is outside allowed range")
        if isinstance(self.relevance, bool):
            raise ContextContractError("relevance must be numeric")
        relevance = float(self.relevance)
        if not math.isfinite(relevance) or not 0.0 <= relevance <= 1.0:
            raise ContextContractError("relevance must be between 0 and 1")
        object.__setattr__(self, "relevance", relevance)
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))
        _nonnegative_int(self.token_estimate, "token_estimate")
        object.__setattr__(self, "provenance", _refs(self.provenance, "provenance"))
        object.__setattr__(self, "derived_from", _refs(self.derived_from, "derived_from"))
        _text(self.retention_class, "retention_class", max_length=128)
        if not isinstance(self.mandatory, bool):
            raise ContextContractError("mandatory must be boolean")
        if self.schema_version != CONTEXT_SCHEMA_VERSION:
            raise ContextContractError("unsupported context schema version")
        if self.content is not None:
            if not isinstance(self.content, str) or not self.content:
                raise ContextContractError("content must be non-empty when provided")
            if _digest_text(self.content) != self.content_digest:
                raise ContextContractError("content does not match content_digest")
            actual_estimate = estimate_tokens(self.content)
            if self.token_estimate < actual_estimate:
                raise ContextContractError(
                    "token_estimate must not understate conservative estimate"
                )
        if trust is ContextTrust.TRUSTED_CONTROL and kind not in {
            ContextKind.SYSTEM_POLICY,
            ContextKind.PRODUCT_INSTRUCTION,
            ContextKind.OPERATION_OBJECTIVE,
            ContextKind.SKILL_INSTRUCTION,
            ContextKind.TOOL_SCHEMA,
        }:
            raise ContextContractError(
                "trusted_control is not valid for this context kind"
            )
        if self.mandatory and trust is not ContextTrust.TRUSTED_CONTROL:
            raise ContextContractError("mandatory segments must be trusted_control")

    @classmethod
    def from_content(
        cls,
        *,
        segment_id: str,
        kind: ContextKind,
        source_type: str,
        source_id: str,
        content: str,
        trust_level: ContextTrust,
        data_class: str,
        tenant_id: str,
        purpose: str,
        priority: int,
        relevance: float,
        created_at: datetime,
        provenance: Iterable[str],
        retention_class: str,
        content_ref: str | None = None,
        derived_from: Iterable[str] = (),
        mandatory: bool = False,
    ) -> "ContextSegment":
        if not isinstance(content, str) or not content:
            raise ContextContractError("content must be non-empty")
        digest = _digest_text(content)
        return cls(
            segment_id=segment_id,
            kind=kind,
            source_type=source_type,
            source_id=source_id,
            content_ref=content_ref or f"inline-sha256:{digest}",
            content_digest=digest,
            trust_level=trust_level,
            data_class=data_class,
            tenant_id=tenant_id,
            purpose=purpose,
            priority=priority,
            relevance=relevance,
            created_at=created_at,
            token_estimate=estimate_tokens(content),
            provenance=tuple(provenance),
            retention_class=retention_class,
            content=content,
            derived_from=tuple(derived_from),
            mandatory=mandatory,
        )

    def audit_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "segment_id": self.segment_id,
            "kind": self.kind.value,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "content_ref": self.content_ref,
            "content_digest": self.content_digest,
            "trust_level": self.trust_level.value,
            "data_class": self.data_class,
            "tenant_id": self.tenant_id,
            "purpose": self.purpose,
            "priority": self.priority,
            "relevance": self.relevance,
            "created_at": self.created_at.isoformat(),
            "token_estimate": self.token_estimate,
            "provenance": list(self.provenance),
            "retention_class": self.retention_class,
            "derived_from": list(self.derived_from),
            "mandatory": self.mandatory,
        }


@dataclass(frozen=True, slots=True)
class ContextEnvelope:
    context_id: str
    operation_id: str
    execution_id: str
    turn_id: str
    tenant_id: str
    instruction_segments: tuple[ContextSegment, ...]
    evidence_segments: tuple[ContextSegment, ...]
    tool_schema_segments: tuple[ContextSegment, ...]
    budget: ContextBudget
    selected_tokens_estimate: int
    omitted_segment_ids: tuple[str, ...]
    omission_reasons: tuple[tuple[str, str], ...]
    source_snapshot: tuple[tuple[str, str], ...]
    context_digest: str
    compiled_at: datetime
    compiler_version: str
    schema_version: int = CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.context_id, "context_id")
        _uuid(self.operation_id, "operation_id")
        _uuid(self.execution_id, "execution_id")
        _uuid(self.turn_id, "turn_id")
        _text(self.tenant_id, "tenant_id")
        if not isinstance(self.budget, ContextBudget):
            raise ContextContractError("budget must be ContextBudget")
        _nonnegative_int(self.selected_tokens_estimate, "selected_tokens_estimate")
        object.__setattr__(
            self,
            "omitted_segment_ids",
            _refs(self.omitted_segment_ids, "omitted_segment_ids"),
        )
        reasons: list[tuple[str, str]] = []
        for item in self.omission_reasons:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ContextContractError("omission_reasons entries must be pairs")
            reasons.append((_text(item[0], "omission segment id"), _text(item[1], "omission reason")))
        object.__setattr__(self, "omission_reasons", tuple(reasons))
        snapshot: list[tuple[str, str]] = []
        for item in self.source_snapshot:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ContextContractError("source_snapshot entries must be pairs")
            snapshot.append((_text(item[0], "snapshot segment id"), _text(item[1], "snapshot digest", max_length=64)))
        object.__setattr__(self, "source_snapshot", tuple(snapshot))
        digest = _text(self.context_digest, "context_digest", max_length=64)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ContextContractError("context_digest must be lowercase sha256 hex")
        object.__setattr__(self, "compiled_at", _aware(self.compiled_at, "compiled_at"))
        _text(self.compiler_version, "compiler_version", max_length=128)
        if self.schema_version != CONTEXT_SCHEMA_VERSION:
            raise ContextContractError("unsupported context schema version")
        selected = (
            self.instruction_segments
            + self.evidence_segments
            + self.tool_schema_segments
        )
        ids = [segment.segment_id for segment in selected]
        if len(ids) != len(set(ids)):
            raise ContextContractError("selected context segment ids must be unique")
        if any(segment.tenant_id not in {self.tenant_id, "*"} for segment in selected):
            raise ContextContractError("selected segment tenant mismatch")
        if sum(segment.token_estimate for segment in selected) != self.selected_tokens_estimate:
            raise ContextContractError("selected token estimate does not match segments")

    @property
    def selected_segments(self) -> tuple[ContextSegment, ...]:
        return (
            self.instruction_segments
            + self.evidence_segments
            + self.tool_schema_segments
        )

    def binding_dict(self) -> dict[str, Any]:
        """Return the immutable identity that must cross execution boundaries."""

        return {
            "context_id": self.context_id,
            "context_digest": self.context_digest,
            "source_snapshot": [list(item) for item in self.source_snapshot],
            "compiler_version": self.compiler_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
        }

    def audit_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "context_id": self.context_id,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "tenant_id": self.tenant_id,
            "instruction_segment_ids": [
                segment.segment_id for segment in self.instruction_segments
            ],
            "evidence_segment_ids": [
                segment.segment_id for segment in self.evidence_segments
            ],
            "tool_schema_segment_ids": [
                segment.segment_id for segment in self.tool_schema_segments
            ],
            "budget": self.budget.as_dict(),
            "selected_tokens_estimate": self.selected_tokens_estimate,
            "omitted_segment_ids": list(self.omitted_segment_ids),
            "omission_reasons": [list(item) for item in self.omission_reasons],
            "source_snapshot": [list(item) for item in self.source_snapshot],
            "context_digest": self.context_digest,
            "compiled_at": self.compiled_at.isoformat(),
            "compiler_version": self.compiler_version,
        }


def context_digest_payload(
    *,
    operation_id: str,
    execution_id: str,
    turn_id: str,
    tenant_id: str,
    budget: ContextBudget,
    selected: Iterable[ContextSegment],
    omitted_segment_ids: Iterable[str],
    compiler_version: str,
) -> str:
    payload = {
        "operation_id": operation_id,
        "execution_id": execution_id,
        "turn_id": turn_id,
        "tenant_id": tenant_id,
        "budget": budget.as_dict(),
        "selected": [
            {
                "segment_id": segment.segment_id,
                "content_digest": segment.content_digest,
                "kind": segment.kind.value,
                "trust_level": segment.trust_level.value,
                "data_class": segment.data_class,
                "token_estimate": segment.token_estimate,
            }
            for segment in selected
        ],
        "omitted_segment_ids": list(omitted_segment_ids),
        "compiler_version": compiler_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "CONTEXT_SCHEMA_VERSION",
    "ContextBudget",
    "ContextContractError",
    "ContextEnvelope",
    "ContextKind",
    "ContextSegment",
    "ContextTrust",
    "context_digest_payload",
    "estimate_tokens",
]
