"""Canonical VS-001 Functional AI transaction over local inference.

This module binds Skeleton's existing durable cognitive execution state machine
to a credential-free LocalModelAdapter.  It does not create a second agent
runtime; it provides a strict entry point that rejects hosted-provider adapters
and produces compact evidence describing the committed terminal transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Awaitable, Callable, Mapping
from uuid import NAMESPACE_URL, uuid5

from skeleton.ai.runtime.inference import LocalModelAdapter
from skeleton.contracts.ai_execution import AIExecutionRequest, ExecutionState
from skeleton.intelligence.execution_runtime import (
    CognitiveExecutionRuntime,
    ExecutionFinalizationBindings,
    ExecutionRunResult,
    ExecutionVerificationDecision,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_runtime import AsyncToolRuntime


VerificationHook = Callable[
    [AIExecutionRequest, str, str],
    ExecutionVerificationDecision | Awaitable[ExecutionVerificationDecision],
]
FinalizationHook = Callable[
    [AIExecutionRequest, str, Mapping[str, object]],
    ExecutionFinalizationBindings | Awaitable[ExecutionFinalizationBindings],
]


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class FunctionalAIRequest:
    request_id: str
    objective: str
    prompt: str
    instructions: str
    context_digest: str
    allowed_tool_ids: tuple[str, ...] = ()
    data_class: str = "internal"
    tenant_id: str = "default"
    max_model_turns: int = 8
    max_tool_calls: int = 16
    max_repeat_tool_batches: int = 1
    created_at: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __post_init__(self) -> None:
        for name in ("request_id", "objective", "prompt", "instructions", "tenant_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if (
            not isinstance(self.context_digest, str)
            or len(self.context_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.context_digest)
        ):
            raise ValueError("context_digest must be lowercase sha256")
        if self.data_class not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError("unsupported data_class")
        for name, maximum in (
            ("max_model_turns", 64),
            ("max_tool_calls", 256),
            ("max_repeat_tool_batches", 16),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be in [1, {maximum}]")
        tools = tuple(dict.fromkeys(str(item).strip() for item in self.allowed_tool_ids))
        if any(not item for item in tools):
            raise ValueError("allowed_tool_ids must be non-empty")
        object.__setattr__(self, "allowed_tool_ids", tools)
        instant = self.created_at
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        object.__setattr__(self, "created_at", instant.astimezone(timezone.utc))

    @property
    def execution_id(self) -> str:
        return str(uuid5(NAMESPACE_URL, "skeleton-vs001-execution:" + self.request_id))

    @property
    def operation_id(self) -> str:
        return str(uuid5(NAMESPACE_URL, "skeleton-vs001-operation:" + self.request_id))

    def to_execution_request(self) -> AIExecutionRequest:
        return AIExecutionRequest(
            operation_id=self.operation_id,
            execution_id=self.execution_id,
            objective=self.objective.strip(),
            context_policy={
                "tenant_id": self.tenant_id.strip(),
                "data_class": self.data_class,
                "capability": "vs001.functional_ai",
            },
            tool_policy={
                "tenant_id": self.tenant_id.strip(),
                "data_class": self.data_class,
                "purpose": "functional-ai-tool-execution",
                "allowed_tool_ids": list(self.allowed_tool_ids),
            },
            resource_budget={
                "max_model_turns": self.max_model_turns,
                "max_tool_calls": self.max_tool_calls,
            },
            stop_policy={
                "max_repeat_tool_batches": self.max_repeat_tool_batches,
            },
            created_at=self.created_at,
        )


@dataclass(frozen=True, slots=True)
class FunctionalAIEvidence:
    execution_id: str
    operation_id: str
    state: str
    status: str
    local_model_id: str
    local_model_digest: str
    final_output_digest: str
    tool_receipt_count: int
    provider_receipts: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    stream_terminal_event: str
    result_digest: str

    def __post_init__(self) -> None:
        for name in (
            "execution_id",
            "operation_id",
            "state",
            "status",
            "local_model_id",
            "stream_terminal_event",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        for name in ("local_model_digest", "final_output_digest", "result_digest"):
            value = getattr(self, name)
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"{name} must be lowercase sha256")
        if not all(ref.startswith("provider:local:") for ref in self.provider_receipts):
            raise ValueError("VS-001 provider receipts must all be local")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.vs001.evidence.v1",
            "execution_id": self.execution_id,
            "operation_id": self.operation_id,
            "state": self.state,
            "status": self.status,
            "local_model_id": self.local_model_id,
            "local_model_digest": self.local_model_digest,
            "final_output_digest": self.final_output_digest,
            "tool_receipt_count": self.tool_receipt_count,
            "provider_receipts": list(self.provider_receipts),
            "evidence_refs": list(self.evidence_refs),
            "stream_terminal_event": self.stream_terminal_event,
            "result_digest": self.result_digest,
        }


@dataclass(frozen=True, slots=True)
class FunctionalAIRun:
    execution: ExecutionRunResult
    evidence: FunctionalAIEvidence


class FunctionalAIRuntime:
    """Strict local-model entry point for the canonical cognitive runtime."""

    def __init__(
        self,
        repository: SQLiteExecutionRepository,
        local_model: LocalModelAdapter,
        tools: AsyncToolRuntime,
        *,
        verification_hook: VerificationHook,
        finalization_binding_hook: FinalizationHook | None = None,
    ) -> None:
        if not isinstance(repository, SQLiteExecutionRepository):
            raise TypeError("repository must be SQLiteExecutionRepository")
        if not isinstance(local_model, LocalModelAdapter):
            raise TypeError("VS-001 requires LocalModelAdapter")
        if local_model.provider_id != "local":
            raise ValueError("VS-001 provider identity must be local")
        if not isinstance(tools, AsyncToolRuntime):
            raise TypeError("tools must be AsyncToolRuntime")
        if not callable(verification_hook):
            raise TypeError("VS-001 requires an independent verification hook")
        self.repository = repository
        self.local_model = local_model
        self.tools = tools
        self.runtime = CognitiveExecutionRuntime(
            repository,
            local_model,
            tools,
            verification_hook=verification_hook,
            finalization_binding_hook=finalization_binding_hook,
        )

    async def execute(self, request: FunctionalAIRequest) -> FunctionalAIRun:
        if not isinstance(request, FunctionalAIRequest):
            raise TypeError("request must be FunctionalAIRequest")
        result = await self.runtime.start(
            request.to_execution_request(),
            instructions=request.instructions,
            prompt=request.prompt,
            context_digest=request.context_digest,
            now=request.created_at,
        )
        if result.state is not ExecutionState.COMPLETED or result.result is None:
            raise RuntimeError(f"VS-001 did not complete: {result.state.value}")
        terminal = result.result
        if terminal.status != "completed" or terminal.final_output is None:
            raise RuntimeError("VS-001 terminal result is not completed")
        if terminal.stream_terminal_event is None:
            raise RuntimeError("VS-001 lost terminal stream identity")
        if not terminal.provider_receipts:
            raise RuntimeError("VS-001 has no local model receipt")
        if not all(ref.startswith("provider:local:") for ref in terminal.provider_receipts):
            raise RuntimeError("VS-001 crossed into a hosted provider")
        stored = self.repository.result(request.execution_id)
        if stored is None or stored.as_dict() != terminal.as_dict():
            raise RuntimeError("VS-001 durable terminal state diverged")

        result_payload = terminal.as_dict()
        evidence = FunctionalAIEvidence(
            execution_id=request.execution_id,
            operation_id=request.operation_id,
            state=result.state.value,
            status=terminal.status,
            local_model_id=self.local_model.model,
            local_model_digest=self.local_model.engine.model.model_digest,
            final_output_digest=hashlib.sha256(
                terminal.final_output.encode("utf-8")
            ).hexdigest(),
            tool_receipt_count=len(terminal.tool_receipts),
            provider_receipts=terminal.provider_receipts,
            evidence_refs=terminal.evidence_refs,
            stream_terminal_event=terminal.stream_terminal_event,
            result_digest=_digest(result_payload),
        )
        return FunctionalAIRun(execution=result, evidence=evidence)


__all__ = [
    "FunctionalAIEvidence",
    "FunctionalAIRequest",
    "FunctionalAIRun",
    "FunctionalAIRuntime",
]
