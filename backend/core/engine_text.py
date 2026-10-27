"""Reusable backend compatibility adapter for tool-free engine text execution.

This module is the migration surface for legacy backend text callers. It owns
neither provider credentials nor provider transports. It compiles immutable
context, applies bounded budgets, and delegates to the canonical engine client.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from core.route_privacy import require_route_provider_transfer
from core.model_catalog import (
    model_catalog,
    resolve_selection,
    context_budget_for_selection,
    estimate_context_tokens,
    cooperation_context_selection,
    cooperation_context_budget,
    ModelSelectionError,
)
from core.engine_client import (
    EngineClient,
    EngineClientError,
    EngineNotFoundError,
    EngineTerminalResult,
    command_from_context,
)
from skeleton.contracts.context import (
    ContextBudget,
    ContextKind,
    ContextSegment,
    ContextTrust,
)
from skeleton.context.compiler import ContextCompiler, ContextCompilationError, project_provider_context
from skeleton.context.instruction_policy import InstructionPolicy
from skeleton.vault.data_governance import DataGovernanceDenied
from skeleton.skills.tool_contract import validate_json_schema


class EngineTextError(RuntimeError):
    """A backend compatibility text request cannot be executed safely."""


class EngineTextContextError(EngineTextError):
    """The current prompt/framing was not admitted by canonical context policy."""

    code = "engine_context_too_small"


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
    instruction_policy_id: str | None = None
    instruction_policy_version: str | None = None
    history: tuple[Mapping[str, str], ...] = ()
    evidence: tuple[Mapping[str, str], ...] = ()
    tenant_id: str = "default"
    actor_id: str = "backend-ai"
    capability: str = "assistant.compat"
    verification_profile: str = "assistant_proposal"
    max_output_tokens: int | None = None
    data_class: str = "internal"
    purpose: str = "model-inference"
    provider_id: str | None = None
    model_id: str | None = None
    temperature: float | None = None

    structured_output_schema: Mapping[str, Any] | None = None
    cooperation: Mapping[str, Any] | None = None
    max_model_turns: int = 4

    def __post_init__(self) -> None:
        if type(self.max_model_turns) is not int or not 1 <= self.max_model_turns <= 4:
            raise EngineTextError("max_model_turns may only lower the existing limit within [1,4]")
        if self.cooperation is not None:
            from skeleton.intelligence.cooperation import normalize_cooperation_policy

            try:
                object.__setattr__(self, "cooperation", normalize_cooperation_policy(self.cooperation))
            except (TypeError, ValueError) as exc:
                raise EngineTextError("cooperation policy is invalid") from exc
        if (self.provider_id is None) != (self.model_id is None):
            raise EngineTextError("provider_id and model_id must be supplied together")
        for field_name, maximum in (("provider_id", 128), ("model_id", 256)):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name, maximum=maximum))
        if self.temperature is not None and (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(self.temperature)
            or not 0 <= self.temperature <= 2
        ):
            raise EngineTextError("temperature must be finite in [0,2]")
        if self.structured_output_schema is not None:
            try:
                encoded = json.dumps(
                    dict(self.structured_output_schema),
                    allow_nan=False,
                    ensure_ascii=False,
                )
                if len(encoded.encode()) > 65536:
                    raise ValueError("structured output schema exceeds64KiB")
                schema = validate_json_schema(json.loads(encoded))
            except (TypeError, ValueError, RecursionError) as exc:
                raise EngineTextError("structured output schema is invalid") from exc
            object.__setattr__(self, "structured_output_schema", schema)
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
        policy_identity = (
            self.instruction_policy_id,
            self.instruction_policy_version,
        )
        if any(value is not None for value in policy_identity) and not all(
            value is not None for value in policy_identity
        ):
            raise EngineTextError("instruction policy id and version must be supplied together")
        if self.instruction_policy_id is not None:
            object.__setattr__(
                self,
                "instruction_policy_id",
                _text(
                    self.instruction_policy_id,
                    "instruction_policy_id",
                    maximum=256,
                ),
            )
            object.__setattr__(
                self,
                "instruction_policy_version",
                _text(
                    self.instruction_policy_version,
                    "instruction_policy_version",
                    maximum=64,
                ),
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
            raise EngineTextError("engine text compatibility requires an assistant capability")
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
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1 or raw > 131_072:
                raise EngineTextError("max_output_tokens is outside allowed range")
        normalized_history: list[dict[str, str]] = []
        history_bytes = 0
        for index, item in enumerate(self.history):
            if not isinstance(item, Mapping):
                raise EngineTextError(f"history[{index}] must be an object")
            role = _text(
                item.get("role"),
                f"history[{index}].role",
                maximum=32,
            )
            if role not in {"user", "assistant"}:
                raise EngineTextError(f"history[{index}].role is unsupported")
            content = _text(
                item.get("content"),
                f"history[{index}].content",
                maximum=1_000_000,
            )
            normalized_history.append({"role": role, "content": content})
            history_bytes += len(content.encode("utf-8"))
            if history_bytes > 512 * 1024:
                raise EngineTextError("history exceeds maximum aggregate UTF-8 bytes")
            if len(normalized_history) > 100:
                raise EngineTextError("history exceeds maximum turn count")
        object.__setattr__(self, "history", tuple(normalized_history))

        normalized_evidence: list[dict[str, str]] = []
        seen_evidence_ids: set[str] = set()
        total_evidence_chars = 0
        for index, item in enumerate(self.evidence):
            if not isinstance(item, Mapping):
                raise EngineTextError(f"evidence[{index}] must be an object")
            source_id = _text(
                item.get("source_id"),
                f"evidence[{index}].source_id",
                maximum=512,
            )
            if source_id in seen_evidence_ids:
                raise EngineTextError("evidence source_id values must be unique")
            seen_evidence_ids.add(source_id)
            content = _text(
                item.get("content"),
                f"evidence[{index}].content",
                maximum=200_000,
            )
            kind = str(item.get("kind") or "retrieval_evidence").strip().lower()
            if kind not in {"retrieval_evidence", "artifact"}:
                raise EngineTextError(f"evidence[{index}].kind is unsupported")
            total_evidence_chars += len(content)
            if total_evidence_chars > 1_000_000:
                raise EngineTextError("evidence exceeds maximum aggregate size")
            normalized_evidence.append(
                {
                    "source_id": source_id,
                    "content": content,
                    "kind": kind,
                }
            )
            if len(normalized_evidence) > 256:
                raise EngineTextError("evidence exceeds maximum segment count")
        object.__setattr__(
            self,
            "evidence",
            tuple(normalized_evidence),
        )

    @property
    def request_identity_digest(self) -> str:
        encoded = json.dumps(
            {
                "instructions": self.instructions,
                "prompt": self.prompt,
                "history": self.history,
                "evidence": self.evidence,
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
                "instruction_policy_id": self.instruction_policy_id,
                "instruction_policy_version": self.instruction_policy_version,
                "verification_profile": self.verification_profile,
                "data_class": self.data_class,
                "purpose": self.purpose,
                **(
                    {}
                    if self.structured_output_schema is None
                    else {"structured_output_schema": self.structured_output_schema}
                ),
                **({} if self.cooperation is None else {"cooperation": self.cooperation}),
                **({} if self.max_model_turns == 4 else {"max_model_turns": self.max_model_turns}),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class EngineTextResponse:
    # Preserve the historical compatibility constructor while carrying the
    # complete canonical engine lineage for callers that need to persist it.
    text: str
    execution_id: str
    verification: str | None
    evidence_refs: tuple[str, ...]
    usage: Mapping[str, object]
    operation_id: str | None = None
    context_id: str | None = None
    context_digest: str | None = None
    context_source_snapshot: tuple[tuple[str, str], ...] = ()
    context_compiler_version: str | None = None
    provider_receipts: tuple[str, ...] = ()
    tool_receipts: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()


_DATA_CLASS_ORDER = (
    "public",
    "internal",
    "confidential",
    "restricted",
)


def _effective_data_class(request: EngineTextRequest) -> str:
    # EngineText's canonical instruction policy is internal by default; all
    # history/evidence/prompt segments inherit request.data_class.
    return max(
        ("internal", request.data_class),
        key=_DATA_CLASS_ORDER.index,
    )


def _terminal_response(
    *,
    request: EngineTextRequest,
    terminal: EngineTerminalResult,
    binding,
    operation_id: str,
    execution_id: str,
    turn_id: str,
) -> EngineTextResponse:
    prompt_digest = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()
    expected_prompt = (
        _stable_uuid("backend-engine-prompt", operation_id + ":prompt:" + request.request_identity_digest),
        prompt_digest,
    )
    legacy_prompt = (_stable_uuid("backend-engine-prompt", operation_id + ":prompt"), prompt_digest)
    snapshot = set(binding.source_snapshot)
    if expected_prompt not in snapshot and not (
        request.provider_id is None
        and request.model_id is None
        and request.temperature is None
        and request.structured_output_schema is None
        and request.cooperation is None
        and request.max_model_turns == 4
        and legacy_prompt in snapshot
    ):
        raise EngineTextError("chat idempotency identity was reused with different request semantics")
    if (
        terminal.operation_id != operation_id
        or terminal.execution_id != execution_id
        or binding.operation_id != operation_id
        or binding.execution_id != execution_id
        or binding.turn_id != turn_id
        or binding.trace_id != "engine-text:" + operation_id
        or binding.tenant_id != request.tenant_id
        or binding.actor_id != request.actor_id
        or binding.capability != request.capability
        or binding.idempotency_key != request.idempotency_key
        or binding.purpose != request.purpose
        or binding.data_class != _effective_data_class(request)
    ):
        raise EngineTextError("canonical engine terminal/handoff identity diverged from request")
    _validate_cooperation_terminal(request, terminal, binding.source_snapshot)
    return EngineTextResponse(
        text=terminal.final_output,
        operation_id=terminal.operation_id,
        execution_id=terminal.execution_id,
        context_id=binding.context_id,
        context_digest=binding.context_digest,
        context_source_snapshot=binding.source_snapshot,
        context_compiler_version=binding.compiler_version,
        verification=terminal.verification,
        evidence_refs=terminal.evidence_refs,
        provider_receipts=terminal.provider_receipts,
        tool_receipts=terminal.tool_receipts,
        memory_refs=terminal.memory_refs,
        artifact_refs=terminal.artifact_refs,
        usage=dict(terminal.usage),
    )


def _validate_cooperation_terminal(request, terminal, source_snapshot) -> None:
    if request.cooperation is None:
        return
    from skeleton.intelligence.cooperation import validate_cooperation_summary

    try:
        validate_cooperation_summary(
            terminal.usage.get("cooperation"),
            request.cooperation,
            source_snapshot,
            terminal.provider_receipts,
            expected_brief_digest=hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise EngineTextError("canonical cooperation result evidence is invalid") from exc


def _policy(request: EngineTextRequest) -> InstructionPolicy:
    digest = hashlib.sha256(request.instructions.encode("utf-8")).hexdigest()
    return InstructionPolicy(
        policy_id=(request.instruction_policy_id or ("backend.engine.compat." + digest[:24])),
        version=request.instruction_policy_version or "1",
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
        kind = ContextKind.USER_MESSAGE if role == "user" else ContextKind.ASSISTANT_MESSAGE
        trust = ContextTrust.AUTHORIZED_USER_DATA if role == "user" else ContextTrust.DERIVED_UNTRUSTED
        segments.append(
            ContextSegment.from_content(
                segment_id=_stable_uuid(
                    "backend-engine-history",
                    operation_id + ":" + str(index),
                ),
                kind=kind,
                source_type="legacy-engine-history",
                source_id=("legacy-history:" + request.idempotency_key + ":" + str(index)),
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
    for index, item in enumerate(request.evidence):
        kind = ContextKind.ARTIFACT if item["kind"] == "artifact" else ContextKind.RETRIEVAL_EVIDENCE
        segments.append(
            ContextSegment.from_content(
                segment_id=_stable_uuid(
                    "backend-engine-evidence",
                    operation_id + ":" + str(index) + ":" + item["source_id"],
                ),
                kind=kind,
                source_type="backend-engine-evidence",
                source_id=item["source_id"],
                content=item["content"],
                trust_level=ContextTrust.DERIVED_UNTRUSTED,
                data_class=request.data_class,
                tenant_id=request.tenant_id,
                purpose=request.purpose,
                priority=700,
                relevance=0.9,
                created_at=created_at,
                provenance=("backend-engine-text", "product-evidence"),
                retention_class="ephemeral-engine-evidence",
            )
        )
    segments.append(
        ContextSegment.from_content(
            segment_id=_stable_uuid(
                "backend-engine-prompt",
                operation_id + ":prompt:" + request.request_identity_digest,
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
    # Frozen dataclasses still contain caller-readable mappings. Revalidate and
    # detach their complete nested payload before the first await so a caller
    # cannot change recovery identity or role selections during catalog I/O.
    request = replace(request)
    try:
        require_route_provider_transfer(
            provider_id="skeleton-engine",
            data_class=request.data_class,
            purpose=request.purpose,
            tenant_id=request.tenant_id,
            source="backend.engine_text",
        )
    except DataGovernanceDenied as exc:
        raise EngineTextError("route privacy denied engine text request") from exc
    active_client = client
    if active_client is None:
        try:
            active_client = EngineClient.from_env()
        except EngineClientError as exc:
            raise EngineTextError("canonical engine configuration is invalid") from exc
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

    # Recovery precedes context compilation. Product evidence/retrieval may
    # change between attempts, but an already-admitted canonical execution is
    # immutable truth for this idempotency identity. Lightweight injected test
    # clients may omit recovery APIs; the real EngineClient must expose them.
    recovery_capable = all(
        callable(getattr(active_client, name, None))
        for name in (
            "terminal_result_if_available",
            "wait_for_terminal",
            "handoff_binding",
        )
    )
    if recovery_capable:
        try:
            terminal = await active_client.terminal_result_if_available(
                execution_id=execution_id,
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                trace_id="engine-text:" + operation_id,
            )
            if terminal is None:
                terminal = await active_client.wait_for_terminal(
                    execution_id=execution_id,
                    actor_id=request.actor_id,
                    tenant_id=request.tenant_id,
                    trace_id="engine-text:" + operation_id,
                )
            binding = await active_client.handoff_binding(
                execution_id,
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                trace_id="engine-text:" + operation_id,
            )
            return _terminal_response(
                request=request,
                terminal=terminal,
                binding=binding,
                operation_id=operation_id,
                execution_id=execution_id,
                turn_id=turn_id,
            )
        except EngineNotFoundError:
            pass
        except EngineClientError as exc:
            raise EngineTextError("canonical engine recovery failed") from exc
    policy = _policy(request)
    catalog = await model_catalog(active_client, actor_id=request.actor_id, tenant_id=request.tenant_id)
    try:
        selection = resolve_selection(catalog, provider_id=request.provider_id, model_id=request.model_id)
        selection = cooperation_context_selection(
            catalog, selection, request.cooperation, output_tokens=request.max_output_tokens
        )
        budget = context_budget_for_selection(selection, output_tokens=request.max_output_tokens)
        budget = cooperation_context_budget(budget, request.cooperation)
        if request.temperature is not None and selection.get("supports_temperature") is not True:
            raise ModelSelectionError("model_temperature_unsupported")
    except ModelSelectionError as exc:
        raise EngineTextError("canonical model selection or context settings are unavailable") from exc
    segments = _context_segments(request, policy=policy, operation_id=operation_id, created_at=now)
    segments = tuple(
        replace(
            segment,
            token_estimate=max(segment.token_estimate, estimate_context_tokens(segment.content, selection)),
        )
        for segment in segments
    )
    try:
        envelope = ContextCompiler().compile(
            operation_id=operation_id,
            execution_id=execution_id,
            turn_id=turn_id,
            tenant_id=request.tenant_id,
            purpose=request.purpose,
            budget=budget,
            segments=segments,
            tools_enabled=False,
            compiled_at=now,
        )
    except ContextCompilationError as exc:
        raise EngineTextContextError("current request cannot fit the selected model context policy") from exc
    expected_prompt = (
        _stable_uuid("backend-engine-prompt", operation_id + ":prompt:" + request.request_identity_digest),
        hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
    )
    selected_prompts = {
        (segment.segment_id, segment.content_digest)
        for segment in envelope.evidence_segments
        if segment.kind is ContextKind.USER_MESSAGE
    }
    projection = project_provider_context(envelope)
    if expected_prompt not in selected_prompts or projection.prompt != request.prompt:
        raise EngineTextContextError("current prompt does not fit the selected model context")
    if selection["context_tokenizer"] in {"utf8_bytes", "reference_tokens"}:
        from skeleton.ai.runtime.inference.local import LocalInferenceRequest, _TOKEN

        rendered = LocalInferenceRequest(
            prompt=projection.prompt,
            instructions=projection.instructions,
            history=tuple((item["role"], item["content"]) for item in projection.history),
        ).rendered_input
        estimate = (
            len(rendered.encode("utf-8")) + 1
            if selection["context_tokenizer"] == "utf8_bytes"
            else sum(1 for _ in _TOKEN.finditer(rendered))
        )
        if estimate > envelope.budget.input_capacity(tools_enabled=False):
            raise EngineTextContextError("complete framed conversation does not fit the selected model")
    command = command_from_context(
        context=envelope,
        actor_id=request.actor_id,
        capability=request.capability,
        idempotency_key=request.idempotency_key,
        instructions=policy.instructions,
        prompt=request.prompt,
        objective="Execute tool-free backend assistant compatibility request",
        verification_profile=request.verification_profile,
        history=(),
        service_principal=active_client.config.service_principal,
        created_at=now,
        deadline=now + timedelta(seconds=active_client.config.execution_timeout_s),
        trace_id="engine-text:" + operation_id,
        max_model_turns=request.max_model_turns,
        max_output_tokens=budget.reserved_output_tokens,
        provider_id=selection["selection_provider_id"],
        model_id=selection["selection_model_id"],
        temperature=request.temperature,
        structured_output_schema=request.structured_output_schema,
        cooperation=request.cooperation,
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
    if recovery_capable:
        try:
            binding = await active_client.handoff_binding(
                execution_id,
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                trace_id="engine-text:" + operation_id,
            )
        except EngineClientError as exc:
            raise EngineTextError("canonical engine handoff recovery failed") from exc
        return _terminal_response(
            request=request,
            terminal=terminal,
            binding=binding,
            operation_id=operation_id,
            execution_id=execution_id,
            turn_id=turn_id,
        )

    if terminal.operation_id != operation_id or terminal.execution_id != execution_id:
        raise EngineTextError("canonical engine terminal identity diverged from compiled request")
    _validate_cooperation_terminal(request, terminal, envelope.source_snapshot)
    return EngineTextResponse(
        text=terminal.final_output,
        operation_id=terminal.operation_id,
        execution_id=terminal.execution_id,
        context_id=envelope.context_id,
        context_digest=envelope.context_digest,
        context_source_snapshot=envelope.source_snapshot,
        context_compiler_version=envelope.compiler_version,
        verification=terminal.verification,
        evidence_refs=terminal.evidence_refs,
        provider_receipts=terminal.provider_receipts,
        tool_receipts=terminal.tool_receipts,
        memory_refs=terminal.memory_refs,
        artifact_refs=terminal.artifact_refs,
        usage=dict(terminal.usage),
    )


__all__ = [
    "EngineTextContextError",
    "EngineTextError",
    "EngineTextRequest",
    "EngineTextResponse",
    "execute_engine_text",
]
