"""Reusable backend compatibility adapter for tool-free engine text execution.

This module is the migration surface for legacy backend text callers. It owns
neither provider credentials nor provider transports. It compiles immutable
context, applies bounded budgets, and delegates to the canonical engine client.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from core.engine_client import (
    EngineClient,
    EngineClientError,
    EngineTerminalResult,
    command_from_context,
)
from skeleton.contracts.context import (
    ContextBudget,
    ContextKind,
    ContextSegment,
    ContextTrust,
)
from skeleton.context.compiler import ContextCompiler
from skeleton.context.instruction_policy import InstructionPolicy


class EngineTextError(RuntimeError):
    """A backend compatibility text request cannot be executed safely."""


def _text(value: object, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EngineTextError(f"{field} must be non-empty text")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise EngineTextError(f"{field} exceeds maximum length")
    return normalized


def _stable_uuid(namespace: str, material: str) -> str:
    return str(uuid5(NAMESPACE_URL, namespace + ":" + material))


@dataclass(frozen=True, slots=True)
class EngineTextRequest:
    instructions: str
    prompt: str
    idempotency_key: str
    history: tuple[Mapping[str, str], ...] = ()
    tenant_id: str = "default"
    actor_id: str = "backend-ai"
    capability: str = "assistant.compat"
    verification_profile: str = "assistant_proposal"
    max_output_tokens: int | None = None
    data_class: str = "internal"
    purpose: str = "model-inference"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instructions",
            _text(self.instructions, "instructions", maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "prompt",
            _text(self.prompt, "prompt", maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _text(self.idempotency_key, "idempotency_key", maximum=1024),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _text(self.tenant_id, "tenant_id", maximum=512),
        )
        object.__setattr__(
            self,
            "actor_id",
            _text(self.actor_id, "actor_id", maximum=512),
        )
        capability = _text(self.capability, "capability", maximum=256)
        if capability not in {"assistant.chat", "assistant.compat"}:
            raise EngineTextError(
                "engine text compatibility requires an assistant capability"
            )
        object.__setattr__(self, "capability", capability)
        profile = _text(
            self.verification_profile,
            "verification_profile",
            maximum=64,
        )
        if profile not in {"assistant_proposal", "evidence_required"}:
            raise EngineTextError("verification_profile is unsupported")
        object.__setattr__(self, "verification_profile", profile)
        if self.data_class not in {
            "public",
            "internal",
            "confidential",
            "restricted",
        }:
            raise EngineTextError("data_class is invalid")
        object.__setattr__(
            self,
            "purpose",
            _text(self.purpose, "purpose", maximum=256),
        )
        if self.max_output_tokens is not None:
            raw = self.max_output_tokens
            if (
                isinstance(raw, bool)
                or not isinstance(raw, int)
                or raw < 1
                or raw > 131_072
            ):
                raise EngineTextError(
                    "max_output_tokens is outside allowed range"
                )
        normalized_history: list[dict[str, str]] = []
        for index, item in enumerate(self.history):
            if not isinstance(item, Mapping):
                raise EngineTextError(f"history[{index}] must be an object")
            role = _text(
                item.get("role"),
                f"history[{index}].role",
                maximum=32,
            )
            if role not in {"user", "assistant"}:
                raise EngineTextError(
                    f"history[{index}].role is unsupported"
                )
            content = _text(
                item.get("content"),
                f"history[{index}].content",
                maximum=1_000_000,
            )
            normalized_history.append(
                {"role": role, "content": content}
            )
            if len(normalized_history) > 1024:
                raise EngineTextError("history exceeds maximum turn count")
        object.__setattr__(self, "history", tuple(normalized_history))


@dataclass(frozen=True, slots=True)
class EngineTextResponse:
    text: str
    execution_id: str
    verification: str | None
    evidence_refs: tuple[str, ...]
    usage: Mapping[str, object]


def _policy(request: EngineTextRequest) -> InstructionPolicy:
    digest = hashlib.sha256(
        request.instructions.encode("utf-8")
    ).hexdigest()
    return InstructionPolicy(
        policy_id="backend.engine.compat." + digest[:24],
        version="1",
        instructions=request.instructions,
    )


def _context_segments(
    request: EngineTextRequest,
    *,
    policy: InstructionPolicy,
    operation_id: str,
    created_at: datetime,
) -> tuple[ContextSegment, ...]:
    segments: list[ContextSegment] = [
        policy.to_segment(
            tenant_id="*",
            purpose=request.purpose,
            created_at=created_at,
            mandatory=True,
        )
    ]
    for index, item in enumerate(request.history):
        role = item["role"]
        kind = (
            ContextKind.USER_MESSAGE
            if role == "user"
            else ContextKind.ASSISTANT_MESSAGE
        )
        trust = (
            ContextTrust.AUTHORIZED_USER_DATA
            if role == "user"
            else ContextTrust.DERIVED_UNTRUSTED
        )
        segments.append(
            ContextSegment.from_content(
                segment_id=_stable_uuid(
                    "backend-engine-history",
                    operation_id + ":" + str(index),
                ),
                kind=kind,
                source_type="legacy-engine-history",
                source_id=(
                    "legacy-history:"
                    + request.idempotency_key
                    + ":"
                    + str(index)
                ),
                content=item["content"],
                trust_level=trust,
                data_class=request.data_class,
                tenant_id=request.tenant_id,
                purpose=request.purpose,
                priority=500,
                relevance=0.8,
                created_at=created_at,
                provenance=("backend-engine-text",),
                retention_class="ephemeral-engine-history",
            )
        )
    segments.append(
        ContextSegment.from_content(
            segment_id=_stable_uuid(
                "backend-engine-prompt",
                operation_id + ":prompt",
            ),
            kind=ContextKind.USER_MESSAGE,
            source_type="legacy-engine-request",
            source_id="legacy-request:" + request.idempotency_key,
            content=request.prompt,
            trust_level=ContextTrust.AUTHORIZED_USER_DATA,
            data_class=request.data_class,
            tenant_id=request.tenant_id,
            purpose=request.purpose,
            priority=900,
            relevance=1.0,
            created_at=created_at,
            provenance=("backend-engine-text",),
            retention_class="ephemeral-engine-request",
        )
    )
    return tuple(segments)


async def execute_engine_text(
    request: EngineTextRequest,
    *,
    client: EngineClient | None = None,
) -> EngineTextResponse:
    """Compile and execute one bounded tool-free assistant proposal."""

    if not isinstance(request, EngineTextRequest):
        raise TypeError("request must be EngineTextRequest")
    active_client = client
    if active_client is None:
        try:
            active_client = EngineClient.from_env()
        except EngineClientError as exc:
            raise EngineTextError(
                "canonical engine configuration is invalid"
            ) from exc
    if active_client is None:
        raise EngineTextError("canonical engine is not configured")

    now = datetime.now(timezone.utc)
    identity_material = "|".join(
        (
            request.tenant_id,
            request.actor_id,
            request.capability,
            request.idempotency_key,
        )
    )
    operation_id = _stable_uuid(
        "backend-engine-text-operation",
        identity_material,
    )
    execution_id = _stable_uuid(
        "backend-engine-text-execution",
        operation_id,
    )
    turn_id = _stable_uuid(
        "backend-engine-text-turn",
        operation_id,
    )
    policy = _policy(request)
    output_reserve = min(
        131_072,
        request.max_output_tokens or 16_384,
    )
    budget = ContextBudget(
        max_context_tokens=262_144,
        reserved_output_tokens=output_reserve,
        reserved_tool_result_tokens=0,
        reserved_policy_tokens=4_096,
        safety_margin_tokens=2_048,
        max_segment_tokens=200_000,
        max_artifact_tokens=200_000,
        max_tool_result_tokens=1,
    )
    envelope = ContextCompiler().compile(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id=request.tenant_id,
        purpose=request.purpose,
        budget=budget,
        segments=_context_segments(
            request,
            policy=policy,
            operation_id=operation_id,
            created_at=now,
        ),
        tools_enabled=False,
        compiled_at=now,
    )
    command = command_from_context(
        context=envelope,
        actor_id=request.actor_id,
        capability=request.capability,
        idempotency_key=request.idempotency_key,
        instructions=policy.instructions,
        prompt=request.prompt,
        objective="Execute tool-free backend assistant compatibility request",
        verification_profile=request.verification_profile,
        history=request.history,
        service_principal=active_client.config.service_principal,
        created_at=now,
        deadline=now
        + timedelta(seconds=active_client.config.execution_timeout_s),
        trace_id="engine-text:" + operation_id,
        max_model_turns=4,
        max_output_tokens=request.max_output_tokens,
        max_tool_calls=1,
        max_repeat_tool_batches=1,
        context_seed_refs=(
            "context:" + envelope.context_id,
            "turn:" + envelope.turn_id,
        ),
    )
    try:
        terminal: EngineTerminalResult = await active_client.execute(command)
    except EngineClientError as exc:
        raise EngineTextError("canonical engine text execution failed") from exc
    return EngineTextResponse(
        text=terminal.final_output,
        execution_id=terminal.execution_id,
        verification=terminal.verification,
        evidence_refs=terminal.evidence_refs,
        usage=dict(terminal.usage),
    )


__all__ = [
    "EngineTextError",
    "EngineTextRequest",
    "EngineTextResponse",
    "execute_engine_text",
]
