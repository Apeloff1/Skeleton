"""Provider-neutral contracts for the AI assistant control plane.

This package is a clean-room composition layer. It models product-facing
assistant behaviors (routing, context, permissions, tools, automations and
provenance) without depending on any vendor model implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


ASSISTANT_SCHEMA_VERSION = 1


class AssistantContractError(ValueError):
    """A product-assistant contract violates a fail-closed invariant."""


class CapabilityKind(str, Enum):
    DIRECT_REASONING = "direct_reasoning"
    PUBLIC_WEB = "public_web"
    PERSONAL_CONTEXT = "personal_context"
    FILES = "files"
    EXTERNAL_APP = "external_app"
    ARTIFACT = "artifact"
    AUTOMATION = "automation"
    IMAGE_GENERATION = "image_generation"
    CODE_EXECUTION = "code_execution"


class TrustTier(str, Enum):
    TRUSTED_CONTROL = "trusted_control"
    AUTHORIZED_USER = "authorized_user"
    PRIVATE_RETRIEVED = "private_retrieved"
    PUBLIC_EVIDENCE = "public_evidence"
    TOOL_OUTPUT = "tool_output"
    MODEL_DERIVED = "model_derived"


class SideEffectClass(str, Enum):
    NONE = "none"
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    EXTERNAL_WRITE = "external_write"
    SECURITY_SENSITIVE = "security_sensitive"


class TimingMode(str, Enum):
    EXACT = "exact_schedule"
    FLEXIBLE = "flexible_schedule"
    CONDITION = "condition_watch"


class ArtifactKind(str, Enum):
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    PDF = "pdf"
    IMAGE = "image"
    CODE = "code"
    OTHER = "other"


def _normalized_text(
    value: object,
    field_name: str,
    *,
    minimum: int = 1,
    maximum: int = 65_536,
) -> str:
    if not isinstance(value, str):
        raise AssistantContractError(f"{field_name} must be text")
    normalized = value.strip()
    if len(normalized) < minimum:
        raise AssistantContractError(f"{field_name} is empty")
    if len(normalized) > maximum:
        raise AssistantContractError(f"{field_name} exceeds maximum length")
    return normalized


def _optional_text(
    value: object | None,
    field_name: str,
    *,
    maximum: int = 1024,
) -> str | None:
    if value is None:
        return None
    return _normalized_text(value, field_name, maximum=maximum)


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise AssistantContractError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AssistantContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _stable_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AssistantContractError("value is not deterministic JSON") from exc


def digest_json(value: object) -> str:
    return hashlib.sha256(_stable_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class AssistantRequest:
    """One product-facing request before capability selection."""

    request_id: str
    text: str
    tenant_id: str = "default"
    user_id: str | None = None
    conversation_id: str | None = None
    attachment_refs: tuple[str, ...] = ()
    explicitly_allowed_capabilities: frozenset[CapabilityKind] = frozenset()
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    max_context_chars: int = 96_000
    max_tool_calls: int = 32

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _normalized_text(self.request_id, "request_id", maximum=256)
        )
        object.__setattr__(self, "text", _normalized_text(self.text, "text"))
        object.__setattr__(
            self, "tenant_id", _normalized_text(self.tenant_id, "tenant_id", maximum=256)
        )
        object.__setattr__(
            self, "user_id", _optional_text(self.user_id, "user_id", maximum=256)
        )
        object.__setattr__(
            self,
            "conversation_id",
            _optional_text(self.conversation_id, "conversation_id", maximum=256),
        )
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))

        refs: list[str] = []
        for raw in self.attachment_refs:
            ref = _normalized_text(raw, "attachment_ref", maximum=2048)
            if ref not in refs:
                refs.append(ref)
        if len(refs) > 128:
            raise AssistantContractError("attachment_refs exceeds maximum count")
        object.__setattr__(self, "attachment_refs", tuple(refs))

        allowed: set[CapabilityKind] = set()
        for value in self.explicitly_allowed_capabilities:
            try:
                allowed.add(
                    value if isinstance(value, CapabilityKind) else CapabilityKind(str(value))
                )
            except ValueError as exc:
                raise AssistantContractError("unknown explicitly allowed capability") from exc
        object.__setattr__(self, "explicitly_allowed_capabilities", frozenset(allowed))

        if isinstance(self.max_context_chars, bool) or not isinstance(
            self.max_context_chars, int
        ):
            raise AssistantContractError("max_context_chars must be integer")
        if not 1_024 <= self.max_context_chars <= 2_000_000:
            raise AssistantContractError("max_context_chars outside hard bounds")
        if isinstance(self.max_tool_calls, bool) or not isinstance(self.max_tool_calls, int):
            raise AssistantContractError("max_tool_calls must be integer")
        if not 0 <= self.max_tool_calls <= 256:
            raise AssistantContractError("max_tool_calls outside hard bounds")

        normalized_meta = dict(self.metadata)
        if len(_stable_json(normalized_meta)) > 256 * 1024:
            raise AssistantContractError("metadata exceeds maximum encoded size")
        object.__setattr__(self, "metadata", normalized_meta)

    def binding(self) -> dict[str, object]:
        return {
            "schema_version": ASSISTANT_SCHEMA_VERSION,
            "request_id": self.request_id,
            "text": self.text,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "attachment_refs": list(self.attachment_refs),
            "explicitly_allowed_capabilities": sorted(
                item.value for item in self.explicitly_allowed_capabilities
            ),
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "max_context_chars": self.max_context_chars,
            "max_tool_calls": self.max_tool_calls,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.binding())


@dataclass(frozen=True, slots=True)
class IntentSignals:
    """Deterministic routing signals extracted from the request surface."""

    needs_fresh_public_info: bool = False
    references_personal_history: bool = False
    references_files: bool = False
    requests_external_action: bool = False
    requests_artifact: ArtifactKind | None = None
    requests_future_action: bool = False
    requests_image: bool = False
    requests_code_execution: bool = False
    sensitive_context: bool = False
    explicit_capability_hints: tuple[CapabilityKind, ...] = ()

    def __post_init__(self) -> None:
        hints: list[CapabilityKind] = []
        for raw in self.explicit_capability_hints:
            try:
                value = raw if isinstance(raw, CapabilityKind) else CapabilityKind(str(raw))
            except ValueError as exc:
                raise AssistantContractError("unknown capability hint") from exc
            if value not in hints:
                hints.append(value)
        object.__setattr__(self, "explicit_capability_hints", tuple(hints))

        if self.requests_artifact is not None and not isinstance(
            self.requests_artifact, ArtifactKind
        ):
            try:
                object.__setattr__(
                    self, "requests_artifact", ArtifactKind(str(self.requests_artifact))
                )
            except ValueError as exc:
                raise AssistantContractError("unknown artifact kind") from exc


@dataclass(frozen=True, slots=True)
class CapabilityPlanStep:
    capability: CapabilityKind
    required: bool
    reason_code: str
    order: int
    read_only: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.capability, CapabilityKind):
            object.__setattr__(self, "capability", CapabilityKind(str(self.capability)))
        object.__setattr__(
            self, "reason_code", _normalized_text(self.reason_code, "reason_code", maximum=128)
        )
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise AssistantContractError("plan step order must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class RoutingPlan:
    request_digest: str
    steps: tuple[CapabilityPlanStep, ...]
    direct_answer_allowed: bool
    requires_user_confirmation: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request_digest, str)
            or len(self.request_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.request_digest)
        ):
            raise AssistantContractError("request_digest must be lowercase sha256")

        seen: set[CapabilityKind] = set()
        normalized = sorted(self.steps, key=lambda item: item.order)
        for index, step in enumerate(normalized):
            if not isinstance(step, CapabilityPlanStep):
                raise AssistantContractError("steps must contain CapabilityPlanStep")
            if step.capability in seen:
                raise AssistantContractError("routing plan contains duplicate capability")
            seen.add(step.capability)
            if step.order != index:
                raise AssistantContractError("routing plan orders must be dense from zero")
        object.__setattr__(self, "steps", tuple(normalized))

        required_non_direct = any(
            step.required and step.capability is not CapabilityKind.DIRECT_REASONING
            for step in normalized
        )
        if required_non_direct and self.direct_answer_allowed:
            raise AssistantContractError(
                "direct_answer_allowed cannot bypass a required external capability"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": ASSISTANT_SCHEMA_VERSION,
            "request_digest": self.request_digest,
            "steps": [
                {
                    "capability": step.capability.value,
                    "required": step.required,
                    "reason_code": step.reason_code,
                    "order": step.order,
                    "read_only": step.read_only,
                }
                for step in self.steps
            ],
            "direct_answer_allowed": self.direct_answer_allowed,
            "requires_user_confirmation": self.requires_user_confirmation,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: str
    kind: CapabilityKind
    side_effect: SideEffectClass = SideEffectClass.NONE
    required_scopes: frozenset[str] = frozenset()
    requires_explicit_user_action: bool = False
    max_input_bytes: int = 1_048_576
    max_output_bytes: int = 8_388_608

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capability_id",
            _normalized_text(self.capability_id, "capability_id", maximum=256),
        )
        if not isinstance(self.kind, CapabilityKind):
            object.__setattr__(self, "kind", CapabilityKind(str(self.kind)))
        if not isinstance(self.side_effect, SideEffectClass):
            object.__setattr__(
                self, "side_effect", SideEffectClass(str(self.side_effect))
            )
        scopes = frozenset(
            _normalized_text(scope, "scope", maximum=256)
            for scope in self.required_scopes
        )
        object.__setattr__(self, "required_scopes", scopes)
        for name in ("max_input_bytes", "max_output_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AssistantContractError(f"{name} must be a positive integer")
            if value > 128 * 1024 * 1024:
                raise AssistantContractError(f"{name} exceeds hard bound")

        if self.side_effect in {
            SideEffectClass.EXTERNAL_WRITE,
            SideEffectClass.SECURITY_SENSITIVE,
        } and not self.requires_explicit_user_action:
            raise AssistantContractError(
                "externally consequential capabilities require explicit user action"
            )


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    capability_id: str
    request_digest: str
    granted_scopes: frozenset[str]
    granted_at: datetime
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capability_id",
            _normalized_text(self.capability_id, "capability_id", maximum=256),
        )
        if (
            not isinstance(self.request_digest, str)
            or len(self.request_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.request_digest)
        ):
            raise AssistantContractError("request_digest must be lowercase sha256")
        object.__setattr__(
            self,
            "granted_scopes",
            frozenset(
                _normalized_text(value, "granted_scope", maximum=256)
                for value in self.granted_scopes
            ),
        )
        object.__setattr__(self, "granted_at", _utc(self.granted_at, "granted_at"))
        if self.expires_at is not None:
            expires = _utc(self.expires_at, "expires_at")
            if expires <= self.granted_at:
                raise AssistantContractError("grant expiry must follow grant time")
            object.__setattr__(self, "expires_at", expires)

    def valid_at(self, when: datetime) -> bool:
        instant = _utc(when, "when")
        return self.expires_at is None or instant < self.expires_at


@dataclass(frozen=True, slots=True)
class ContextCandidate:
    source_id: str
    content: str
    trust: TrustTier
    relevance: float
    priority: int
    provenance: tuple[str, ...]
    observed_at: datetime
    expires_at: datetime | None = None
    contains_instruction_like_text: bool = False
    data_class: str = "internal"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_id", _normalized_text(self.source_id, "source_id", maximum=1024)
        )
        object.__setattr__(self, "content", _normalized_text(self.content, "content"))
        if not isinstance(self.trust, TrustTier):
            object.__setattr__(self, "trust", TrustTier(str(self.trust)))
        if isinstance(self.relevance, bool) or not isinstance(
            self.relevance, (int, float)
        ):
            raise AssistantContractError("relevance must be numeric")
        relevance = float(self.relevance)
        if not math.isfinite(relevance) or not 0.0 <= relevance <= 1.0:
            raise AssistantContractError("relevance must be finite in [0, 1]")
        object.__setattr__(self, "relevance", relevance)
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise AssistantContractError("priority must be integer")
        if not -10_000 <= self.priority <= 10_000:
            raise AssistantContractError("priority outside hard bounds")
        provenance = tuple(
            dict.fromkeys(
                _normalized_text(item, "provenance", maximum=2048)
                for item in self.provenance
            )
        )
        if not provenance:
            raise AssistantContractError("context candidate requires provenance")
        if len(provenance) > 256:
            raise AssistantContractError("provenance exceeds maximum count")
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if self.expires_at is not None:
            expires = _utc(self.expires_at, "expires_at")
            if expires <= self.observed_at:
                raise AssistantContractError("expires_at must follow observed_at")
            object.__setattr__(self, "expires_at", expires)
        if self.data_class not in {"public", "internal", "confidential", "restricted"}:
            raise AssistantContractError("unknown data_class")

    def is_expired(self, at: datetime) -> bool:
        instant = _utc(at, "at")
        return self.expires_at is not None and instant >= self.expires_at


@dataclass(frozen=True, slots=True)
class CompiledContext:
    request_digest: str
    candidates: tuple[ContextCandidate, ...]
    omitted_source_ids: tuple[str, ...]
    char_count: int
    digest: str

    def __post_init__(self) -> None:
        if self.char_count != sum(len(item.content) for item in self.candidates):
            raise AssistantContractError("compiled context char_count mismatch")
        expected = digest_json(
            {
                "request_digest": self.request_digest,
                "candidates": [
                    {
                        "source_id": item.source_id,
                        "content": item.content,
                        "trust": item.trust.value,
                        "provenance": list(item.provenance),
                    }
                    for item in self.candidates
                ],
                "omitted_source_ids": list(self.omitted_source_ids),
            }
        )
        if self.digest != expected:
            raise AssistantContractError("compiled context digest mismatch")


@dataclass(frozen=True, slots=True)
class ToolProposal:
    proposal_id: str
    capability_id: str
    arguments: Mapping[str, object]
    request_digest: str
    side_effect: SideEffectClass
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "proposal_id", _normalized_text(self.proposal_id, "proposal_id", maximum=256)
        )
        object.__setattr__(
            self,
            "capability_id",
            _normalized_text(self.capability_id, "capability_id", maximum=256),
        )
        if not isinstance(self.side_effect, SideEffectClass):
            object.__setattr__(
                self, "side_effect", SideEffectClass(str(self.side_effect))
            )
        if (
            not isinstance(self.request_digest, str)
            or len(self.request_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.request_digest)
        ):
            raise AssistantContractError("request_digest must be lowercase sha256")
        args = dict(self.arguments)
        if len(_stable_json(args)) > 1_048_576:
            raise AssistantContractError("tool arguments exceed maximum encoded size")
        object.__setattr__(self, "arguments", args)
        object.__setattr__(
            self,
            "idempotency_key",
            _normalized_text(self.idempotency_key, "idempotency_key", maximum=512),
        )

    @property
    def arguments_digest(self) -> str:
        return digest_json(self.arguments)


@dataclass(frozen=True, slots=True)
class ToolReceipt:
    proposal_id: str
    capability_id: str
    status: str
    output_ref: str | None
    request_digest: str
    arguments_digest: str
    started_at: datetime
    finished_at: datetime
    error_code: str | None = None
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "proposal_id", _normalized_text(self.proposal_id, "proposal_id", maximum=256)
        )
        object.__setattr__(
            self,
            "capability_id",
            _normalized_text(self.capability_id, "capability_id", maximum=256),
        )
        if self.status not in {"succeeded", "failed", "blocked", "cancelled"}:
            raise AssistantContractError("unknown tool receipt status")
        object.__setattr__(
            self, "output_ref", _optional_text(self.output_ref, "output_ref", maximum=2048)
        )
        object.__setattr__(
            self, "error_code", _optional_text(self.error_code, "error_code", maximum=256)
        )
        for name in ("request_digest", "arguments_digest"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise AssistantContractError(f"{name} must be lowercase sha256")
        start = _utc(self.started_at, "started_at")
        finish = _utc(self.finished_at, "finished_at")
        if finish < start:
            raise AssistantContractError("finished_at cannot precede started_at")
        object.__setattr__(self, "started_at", start)
        object.__setattr__(self, "finished_at", finish)
        object.__setattr__(
            self,
            "provenance",
            tuple(
                dict.fromkeys(
                    _normalized_text(item, "provenance", maximum=2048)
                    for item in self.provenance
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class AutomationIntent:
    title: str
    instruction: str
    timing_mode: TimingMode
    schedule: str | None = None
    relative_offset: Mapping[str, int] | None = None
    condition_description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _normalized_text(self.title, "title", maximum=128))
        object.__setattr__(
            self, "instruction", _normalized_text(self.instruction, "instruction", maximum=8192)
        )
        if not isinstance(self.timing_mode, TimingMode):
            object.__setattr__(self, "timing_mode", TimingMode(str(self.timing_mode)))
        object.__setattr__(
            self, "schedule", _optional_text(self.schedule, "schedule", maximum=8192)
        )
        object.__setattr__(
            self,
            "condition_description",
            _optional_text(
                self.condition_description, "condition_description", maximum=4096
            ),
        )
        offset = None if self.relative_offset is None else dict(self.relative_offset)
        if offset is not None:
            allowed = {
                "years",
                "months",
                "weeks",
                "days",
                "hours",
                "minutes",
                "seconds",
            }
            if not offset or not set(offset) <= allowed:
                raise AssistantContractError("relative_offset contains unsupported fields")
            for key, value in offset.items():
                if isinstance(value, bool) or not isinstance(value, int):
                    raise AssistantContractError("relative_offset values must be integers")
            object.__setattr__(self, "relative_offset", offset)

        supplied = sum(
            value is not None
            for value in (self.schedule, self.relative_offset, self.condition_description)
        )
        if self.timing_mode is TimingMode.CONDITION:
            if self.condition_description is None:
                raise AssistantContractError("condition watch requires condition description")
            if self.relative_offset is not None:
                raise AssistantContractError("condition watch cannot use relative offset")
        elif supplied != 1:
            raise AssistantContractError(
                "time-based automation requires exactly one schedule or relative offset"
            )


def deterministic_id(prefix: str, *parts: object) -> str:
    prefix_value = _normalized_text(prefix, "prefix", maximum=64)
    payload = [str(part) for part in parts]
    return f"{prefix_value}:{digest_json(payload)}"


__all__ = [
    "ASSISTANT_SCHEMA_VERSION",
    "ArtifactKind",
    "AssistantContractError",
    "AssistantRequest",
    "AutomationIntent",
    "CapabilityDescriptor",
    "CapabilityGrant",
    "CapabilityKind",
    "CapabilityPlanStep",
    "CompiledContext",
    "ContextCandidate",
    "IntentSignals",
    "RoutingPlan",
    "SideEffectClass",
    "TimingMode",
    "ToolProposal",
    "ToolReceipt",
    "TrustTier",
    "deterministic_id",
    "digest_json",
]
