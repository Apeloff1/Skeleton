"""Canonical conversation/context bridge for the standalone local AI path.

The initial product-completion layer proves a portable durable conversation
boundary.  This module goes one level deeper and deliberately reuses Skeleton's
existing canonical conversation authority and context compiler so the direct
local Functional AI path does not invent a second product-state or trust model.

Authority remains split intentionally:
- ConversationThread / ConversationMessage own product history and lineage.
- ContextCompiler owns trust, budgeting, source snapshots and provider projection.
- FunctionalAIRuntime / CognitiveExecutionRuntime own model/tool execution.
- This bridge owns correlation and the crash-safe handoff between those planes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from skeleton.ai.runtime.functional_ai import (
    FunctionalAIEvidence,
    FunctionalAIRequest,
    FunctionalAIRuntime,
)
from skeleton.contracts.ai_execution import ExecutionState
from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
)
from skeleton.context.compiler import (
    ContextCompiler as CanonicalContextCompiler,
    project_provider_context,
)
from skeleton.context.instruction_policy import InstructionPolicy
from skeleton.context.sources import conversation_message_segment
from skeleton.intelligence.execution_runtime import ExecutionRunResult
from skeleton.persistence.conversation_repository import (
    ConversationConflict,
    ConversationRepositoryCorruption,
    SQLiteConversationRepository,
)
from skeleton.provider_runtime import AIMessage


_PURPOSE = "model-inference"
_ALLOWED_EXTERNAL_CONTEXT_KINDS = frozenset(
    {
        ContextKind.MEMORY,
        ContextKind.RETRIEVAL_EVIDENCE,
        ContextKind.ARTIFACT,
        ContextKind.CONVERSATION_SUMMARY,
    }
)

CANONICAL_PRODUCT_CONTEXT_BUDGET = ContextBudget(
    max_context_tokens=128_000,
    reserved_output_tokens=4_096,
    reserved_tool_result_tokens=8_192,
    reserved_policy_tokens=2_048,
    safety_margin_tokens=1_024,
    max_segment_tokens=40_000,
    max_artifact_tokens=16_000,
    max_tool_result_tokens=16_000,
)


class CanonicalProductRuntimeError(RuntimeError):
    """The canonical product-to-functional-AI bridge cannot safely continue."""


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _json_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _functional_request_id(thread_id: str, user_message_id: str) -> str:
    return f"canonical-product:{thread_id}:{user_message_id}"


def _functional_execution_id(request_id: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-vs001-execution:" + request_id,
        )
    )


def _functional_operation_id(request_id: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-vs001-operation:" + request_id,
        )
    )


@dataclass(frozen=True, slots=True)
class CanonicalAITurnRequest:
    """One product turn against canonical conversation authority.

    external_context_segments are evidence-only.  Product callers cannot inject
    trusted control, conversation messages, tool schemas, or tool results here;
    those have separate canonical owners.
    """

    message: str
    idempotency_key: str
    expected_thread_version: int
    external_context_segments: tuple[ContextSegment, ...] = ()
    attachment_refs: tuple[str, ...] = ()
    allowed_tool_ids: tuple[str, ...] = ()
    approval_refs: tuple[tuple[str, str], ...] = ()
    max_model_turns: int = 8
    max_tool_calls: int = 16
    max_repeat_tool_batches: int = 1
    created_at: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __post_init__(self) -> None:
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be non-empty text")
        if len(self.message) > 100_000:
            raise ValueError("message exceeds canonical conversation limit")
        if (
            not isinstance(self.idempotency_key, str)
            or not self.idempotency_key.strip()
            or self.idempotency_key.strip() != self.idempotency_key
            or len(self.idempotency_key) > 1024
        ):
            raise ValueError("idempotency_key is invalid")
        if (
            isinstance(self.expected_thread_version, bool)
            or not isinstance(self.expected_thread_version, int)
            or self.expected_thread_version < 1
        ):
            raise ValueError("expected_thread_version must be positive")

        external = tuple(self.external_context_segments)
        for segment in external:
            if not isinstance(segment, ContextSegment):
                raise TypeError(
                    "external_context_segments must contain ContextSegment values"
                )
            if segment.trust_level is ContextTrust.TRUSTED_CONTROL:
                raise ValueError(
                    "external context cannot introduce trusted control"
                )
            if segment.kind not in _ALLOWED_EXTERNAL_CONTEXT_KINDS:
                raise ValueError(
                    "external context kind is not product-admissible"
                )
        if len({segment.segment_id for segment in external}) != len(external):
            raise ValueError("external context segment ids must be unique")
        object.__setattr__(self, "external_context_segments", external)

        attachments: list[str] = []
        for raw in self.attachment_refs:
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("attachment_refs must contain non-empty strings")
            value = raw.strip()
            if value.startswith(
                ("product-turn-sha256:", "product-runtime-sha256:")
            ):
                raise ValueError(
                    "attachment_refs cannot use reserved product identity prefix"
                )
            if value not in attachments:
                attachments.append(value)
        if len(attachments) > 256:
            raise ValueError("attachment_refs exceeds canonical reference limit")
        object.__setattr__(self, "attachment_refs", tuple(attachments))

        tools = tuple(dict.fromkeys(str(item).strip() for item in self.allowed_tool_ids))
        if any(not item for item in tools):
            raise ValueError("allowed_tool_ids must be non-empty")
        object.__setattr__(self, "allowed_tool_ids", tools)

        approvals: list[tuple[str, str]] = []
        seen_approval_calls: set[str] = set()
        for raw in self.approval_refs:
            if not isinstance(raw, tuple) or len(raw) != 2:
                raise ValueError("approval_refs entries must be (call_id, approval_ref)")
            call_id = str(raw[0]).strip()
            approval_ref = str(raw[1]).strip()
            if not call_id or not approval_ref:
                raise ValueError("approval_refs entries must be non-empty")
            if call_id in seen_approval_calls:
                raise ValueError("approval_refs contains duplicate call_id")
            seen_approval_calls.add(call_id)
            approvals.append((call_id, approval_ref))
        object.__setattr__(self, "approval_refs", tuple(approvals))

        for name, maximum in (
            ("max_model_turns", 64),
            ("max_tool_calls", 256),
            ("max_repeat_tool_batches", 16),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= maximum
            ):
                raise ValueError(f"{name} must be in [1, {maximum}]")
        object.__setattr__(self, "created_at", _aware(self.created_at))

    @property
    def identity_digest(self) -> str:
        return _json_digest(
            {
                "schema_version": "skeleton.product.canonical-turn.v1",
                "message": self.message,
                "idempotency_key": self.idempotency_key,
                "external_context_segments": [
                    {
                        "segment_id": segment.segment_id,
                        "content_digest": segment.content_digest,
                        "kind": segment.kind.value,
                        "trust_level": segment.trust_level.value,
                        "tenant_id": segment.tenant_id,
                        "purpose": segment.purpose,
                    }
                    for segment in self.external_context_segments
                ],
                "attachment_refs": list(self.attachment_refs),
                "allowed_tool_ids": list(self.allowed_tool_ids),
                "max_model_turns": self.max_model_turns,
                "max_tool_calls": self.max_tool_calls,
                "max_repeat_tool_batches": self.max_repeat_tool_batches,
            }
        )

    @property
    def identity_ref(self) -> str:
        return "product-turn-sha256:" + self.identity_digest


@dataclass(frozen=True, slots=True)
class CanonicalAIResponseEnvelope:
    """Stable response binding canonical product state to execution evidence."""

    thread_id: str
    thread_version: int
    user_message_id: str
    assistant_message_id: str
    operation_id: str
    execution_id: str
    ai_result_id: str
    assistant_text: str
    context_id: str
    context_digest: str
    context_compiler_version: str
    context_source_snapshot: tuple[tuple[str, str], ...]
    local_model_id: str
    local_model_digest: str
    execution_result_digest: str
    evidence_digest: str
    tool_receipt_refs: tuple[str, ...]
    provider_receipt_refs: tuple[str, ...]
    memory_refs: tuple[str, ...]
    citation_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    replayed: bool

    def __post_init__(self) -> None:
        for name in (
            "thread_id",
            "user_message_id",
            "assistant_message_id",
            "operation_id",
            "execution_id",
            "ai_result_id",
            "assistant_text",
            "context_id",
            "context_compiler_version",
            "local_model_id",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if (
            isinstance(self.thread_version, bool)
            or not isinstance(self.thread_version, int)
            or self.thread_version < 1
        ):
            raise ValueError("thread_version must be positive")
        for name in (
            "context_digest",
            "local_model_digest",
            "execution_result_digest",
            "evidence_digest",
        ):
            value = getattr(self, name)
            if (
                len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ValueError(f"{name} must be lowercase sha256")
        if not self.context_source_snapshot:
            raise ValueError("canonical response requires context source snapshot")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.product.canonical-response.v1",
            "thread_id": self.thread_id,
            "thread_version": self.thread_version,
            "user_message_id": self.user_message_id,
            "assistant_message_id": self.assistant_message_id,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "ai_result_id": self.ai_result_id,
            "assistant_text": self.assistant_text,
            "context_id": self.context_id,
            "context_digest": self.context_digest,
            "context_compiler_version": self.context_compiler_version,
            "context_source_snapshot": [
                list(item) for item in self.context_source_snapshot
            ],
            "local_model_id": self.local_model_id,
            "local_model_digest": self.local_model_digest,
            "execution_result_digest": self.execution_result_digest,
            "evidence_digest": self.evidence_digest,
            "tool_receipt_refs": list(self.tool_receipt_refs),
            "provider_receipt_refs": list(self.provider_receipt_refs),
            "memory_refs": list(self.memory_refs),
            "citation_refs": list(self.citation_refs),
            "artifact_refs": list(self.artifact_refs),
            "replayed": self.replayed,
        }


class CanonicalConversationAIRuntime:
    """Join canonical conversation/context authority to the local Functional AI.

    This portable implementation uses SQLiteConversationRepository, mirroring the
    same canonical contracts consumed by the assembled backend's conversation
    authority.  It deliberately does not create an alternative conversation
    schema or context trust model.
    """

    def __init__(
        self,
        conversations: SQLiteConversationRepository,
        functional_runtime: FunctionalAIRuntime,
        *,
        instruction_policy: InstructionPolicy,
        context_budget: ContextBudget = CANONICAL_PRODUCT_CONTEXT_BUDGET,
        context_compiler: CanonicalContextCompiler | None = None,
    ) -> None:
        if not isinstance(conversations, SQLiteConversationRepository):
            raise TypeError("conversations must be SQLiteConversationRepository")
        if not isinstance(functional_runtime, FunctionalAIRuntime):
            raise TypeError("functional_runtime must be FunctionalAIRuntime")
        if not isinstance(instruction_policy, InstructionPolicy):
            raise TypeError("instruction_policy must be InstructionPolicy")
        if not isinstance(context_budget, ContextBudget):
            raise TypeError("context_budget must be ContextBudget")
        self.conversations = conversations
        self.functional_runtime = functional_runtime
        self.instruction_policy = instruction_policy
        self.context_budget = context_budget
        self.context_compiler = context_compiler or CanonicalContextCompiler()
        self._active_tasks: dict[str, asyncio.Task[ExecutionRunResult]] = {}
        self._active_tasks_lock = asyncio.Lock()

    @property
    def runtime_identity_digest(self) -> str:
        return _json_digest(
            {
                "schema_version": "skeleton.product.canonical-runtime.v1",
                "instruction_policy": self.instruction_policy.identity,
                "context_budget": self.context_budget.as_dict(),
                "context_compiler_version": self.context_compiler.compiler_version,
            }
        )

    @property
    def runtime_identity_ref(self) -> str:
        return "product-runtime-sha256:" + self.runtime_identity_digest

    def create_thread(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        title: str = "New conversation",
        data_class: str = "confidential",
        thread_id: str | None = None,
        branch_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ConversationThread:
        return self.conversations.create_thread(
            tenant_id=tenant_id,
            owner_id=owner_id,
            title=title,
            data_class=data_class,
            thread_id=thread_id,
            branch_id=branch_id,
            created_at=created_at,
        )

    def _find_messages(
        self,
        thread: ConversationThread,
        *,
        tenant_id: str,
        owner_id: str,
        idempotency_key: str,
    ) -> tuple[ConversationMessage | None, ConversationMessage | None]:
        after_sequence = max(0, thread.message_sequence - 499)
        recent = self.conversations.list_messages(
            thread.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            after_sequence=after_sequence,
            limit=500,
        )
        user_message = next(
            (
                item
                for item in recent
                if item.author_type is ConversationAuthorType.USER
                and item.idempotency_key == idempotency_key
            ),
            None,
        )
        if user_message is None:
            return None, None
        assistant_key = idempotency_key + ":assistant"
        assistant_message = next(
            (
                item
                for item in recent
                if item.author_type is ConversationAuthorType.ASSISTANT
                and item.causal_user_message_id == user_message.message_id
                and item.idempotency_key == assistant_key
            ),
            None,
        )
        return user_message, assistant_message

    def _append_user(
        self,
        thread: ConversationThread,
        request: CanonicalAITurnRequest,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> tuple[ConversationThread, ConversationMessage]:
        if thread.version != request.expected_thread_version:
            raise ConversationConflict("thread version conflict")
        transcript = self.conversations.active_transcript(
            thread.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if (
            transcript
            and transcript[-1].author_type is ConversationAuthorType.USER
        ):
            raise ConversationConflict(
                "previous canonical turn is incomplete"
            )
        parent = transcript[-1].message_id if transcript else None
        message_id = str(
            uuid5(
                NAMESPACE_URL,
                "skeleton-canonical-product-user:"
                + thread.thread_id
                + ":"
                + request.idempotency_key,
            )
        )
        user_message = ConversationMessage(
            message_id=message_id,
            thread_id=thread.thread_id,
            branch_id=thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.USER,
            created_at=request.created_at,
            idempotency_key=request.idempotency_key,
            content=request.message,
            parent_message_id=parent,
            attachment_refs=(
                *request.attachment_refs,
                request.identity_ref,
                self.runtime_identity_ref,
            ),
            data_class=thread.data_class,
        )
        return self.conversations.append_message(
            user_message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=thread.version,
        )

    def _assert_request_binding(
        self,
        user_message: ConversationMessage,
        request: CanonicalAITurnRequest,
    ) -> None:
        identity_refs = tuple(
            ref
            for ref in user_message.attachment_refs
            if ref.startswith("product-turn-sha256:")
        )
        if len(identity_refs) != 1:
            raise ConversationRepositoryCorruption(
                "canonical user turn is missing unique product request identity"
            )
        if identity_refs[0] != request.identity_ref:
            raise ConversationConflict(
                "idempotency_key was reused with different turn semantics"
            )

        runtime_refs = tuple(
            ref
            for ref in user_message.attachment_refs
            if ref.startswith("product-runtime-sha256:")
        )
        if len(runtime_refs) != 1:
            raise ConversationRepositoryCorruption(
                "canonical user turn is missing unique runtime identity"
            )
        if runtime_refs[0] != self.runtime_identity_ref:
            raise ConversationConflict(
                "canonical turn runtime policy/compiler identity changed"
            )

    async def _run_or_join_execution(
        self,
        *,
        execution_id: str,
        request,
        instructions: str,
        prompt: str,
        context_digest: str,
        history: tuple[AIMessage, ...],
        approval_refs: dict[str, str],
        now: datetime,
    ) -> ExecutionRunResult:
        async with self._active_tasks_lock:
            task = self._active_tasks.get(execution_id)
            if task is None or task.done():
                task = asyncio.create_task(
                    self.functional_runtime.runtime.start(
                        request,
                        instructions=instructions,
                        prompt=prompt,
                        context_digest=context_digest,
                        history=history,
                        approval_refs=approval_refs,
                        now=now,
                    )
                )
                self._active_tasks[execution_id] = task
        try:
            # Product/client cancellation must not accidentally cancel a durable
            # execution. Explicit cancel_turn() owns that authority.
            return await asyncio.shield(task)
        finally:
            if task.done():
                async with self._active_tasks_lock:
                    if self._active_tasks.get(execution_id) is task:
                        self._active_tasks.pop(execution_id, None)

    def _compile_context(
        self,
        *,
        thread: ConversationThread,
        user_message: ConversationMessage,
        tenant_id: str,
        owner_id: str,
        request: CanonicalAITurnRequest,
        operation_id: str,
        execution_id: str,
    ) -> ContextEnvelope:
        transcript = self.conversations.active_transcript(
            thread.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if not transcript or transcript[-1].message_id != user_message.message_id:
            raise ConversationRepositoryCorruption(
                "canonical active transcript does not end at current user turn"
            )

        segments: list[ContextSegment] = [
            self.instruction_policy.to_segment(
                tenant_id="*",
                purpose=_PURPOSE,
                created_at=user_message.created_at,
                mandatory=True,
                provenance=(
                    "conversation-thread:" + thread.thread_id,
                    "conversation-turn:" + user_message.message_id,
                ),
            )
        ]
        segments.extend(
            conversation_message_segment(
                thread,
                message,
                purpose=_PURPOSE,
            )
            for message in transcript
        )
        for segment in request.external_context_segments:
            if segment.tenant_id not in {tenant_id, "*"}:
                raise CanonicalProductRuntimeError(
                    "external context tenant does not match conversation"
                )
            if segment.purpose != _PURPOSE:
                raise CanonicalProductRuntimeError(
                    "external context purpose does not match model inference"
                )
            segments.append(segment)

        return self.context_compiler.compile(
            operation_id=operation_id,
            execution_id=execution_id,
            turn_id=user_message.message_id,
            tenant_id=tenant_id,
            purpose=_PURPOSE,
            budget=self.context_budget,
            segments=segments,
            tools_enabled=bool(request.allowed_tool_ids),
            compiled_at=user_message.created_at,
        )

    def _materialize_evidence(
        self,
        request: FunctionalAIRequest,
        run: ExecutionRunResult,
    ) -> FunctionalAIEvidence:
        if run.state is not ExecutionState.COMPLETED or run.result is None:
            raise CanonicalProductRuntimeError(
                "functional execution did not reach completed state"
            )
        terminal = run.result
        if terminal.status != "completed" or terminal.final_output is None:
            raise CanonicalProductRuntimeError(
                "functional execution has no publishable final output"
            )
        if terminal.stream_terminal_event is None:
            raise CanonicalProductRuntimeError(
                "functional execution lost terminal stream identity"
            )
        if not terminal.provider_receipts:
            raise CanonicalProductRuntimeError(
                "functional execution has no local provider receipt"
            )
        if not all(
            ref.startswith("provider:local:")
            for ref in terminal.provider_receipts
        ):
            raise CanonicalProductRuntimeError(
                "canonical standalone path crossed into hosted provider"
            )
        stored = self.functional_runtime.repository.result(request.execution_id)
        if stored is None or stored.as_dict() != terminal.as_dict():
            raise CanonicalProductRuntimeError(
                "durable functional result diverged from execution result"
            )

        return FunctionalAIEvidence(
            execution_id=request.execution_id,
            operation_id=request.operation_id,
            state=run.state.value,
            status=terminal.status,
            local_model_id=self.functional_runtime.local_model.model,
            local_model_digest=(
                self.functional_runtime.local_model.engine.model.model_digest
            ),
            final_output_digest=hashlib.sha256(
                terminal.final_output.encode("utf-8")
            ).hexdigest(),
            tool_receipt_count=len(terminal.tool_receipts),
            provider_receipts=terminal.provider_receipts,
            evidence_refs=terminal.evidence_refs,
            stream_terminal_event=terminal.stream_terminal_event,
            result_digest=_json_digest(terminal.as_dict()),
        )

    @staticmethod
    def _missing_committed_context() -> str:
        raise ConversationRepositoryCorruption(
            "committed assistant message has no canonical context identity"
        )

    def _response_from_committed(
        self,
        *,
        thread: ConversationThread,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
        evidence: FunctionalAIEvidence,
        terminal,
        replayed: bool,
    ) -> CanonicalAIResponseEnvelope:
        if assistant_message.operation_id != evidence.operation_id:
            raise ConversationRepositoryCorruption(
                "assistant operation identity diverges from execution evidence"
            )
        expected_ai_result_id = "functional-ai-result:" + evidence.result_digest
        if assistant_message.ai_result_id != expected_ai_result_id:
            raise ConversationRepositoryCorruption(
                "assistant AI result identity diverges from execution evidence"
            )
        if assistant_message.content != terminal.final_output:
            raise ConversationRepositoryCorruption(
                "assistant content diverges from durable functional result"
            )
        if tuple(assistant_message.tool_receipt_refs) != tuple(terminal.tool_receipts):
            raise ConversationRepositoryCorruption(
                "assistant tool receipts diverge from durable functional result"
            )
        if tuple(assistant_message.provider_receipt_refs) != tuple(
            terminal.provider_receipts
        ):
            raise ConversationRepositoryCorruption(
                "assistant provider receipts diverge from durable functional result"
            )
        if tuple(assistant_message.citation_refs) != tuple(terminal.evidence_refs):
            raise ConversationRepositoryCorruption(
                "assistant evidence refs diverge from durable functional result"
            )
        return CanonicalAIResponseEnvelope(
            thread_id=thread.thread_id,
            thread_version=thread.version,
            user_message_id=user_message.message_id,
            assistant_message_id=assistant_message.message_id,
            operation_id=evidence.operation_id,
            execution_id=evidence.execution_id,
            ai_result_id=assistant_message.ai_result_id,
            assistant_text=terminal.final_output,
            context_id=assistant_message.context_id or "",
            context_digest=assistant_message.context_digest or "",
            context_compiler_version=assistant_message.context_compiler_version or "",
            context_source_snapshot=assistant_message.context_source_snapshot,
            local_model_id=evidence.local_model_id,
            local_model_digest=evidence.local_model_digest,
            execution_result_digest=evidence.result_digest,
            evidence_digest=_json_digest(evidence.as_dict()),
            tool_receipt_refs=tuple(assistant_message.tool_receipt_refs),
            provider_receipt_refs=tuple(
                assistant_message.provider_receipt_refs
            ),
            memory_refs=tuple(assistant_message.memory_refs),
            citation_refs=tuple(assistant_message.citation_refs),
            artifact_refs=tuple(assistant_message.artifact_refs),
            replayed=replayed,
        )

    async def respond(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        request: CanonicalAITurnRequest,
    ) -> CanonicalAIResponseEnvelope:
        if not isinstance(request, CanonicalAITurnRequest):
            raise TypeError("request must be CanonicalAITurnRequest")
        thread = self.conversations.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        user_message, assistant_message = self._find_messages(
            thread,
            tenant_id=tenant_id,
            owner_id=owner_id,
            idempotency_key=request.idempotency_key,
        )
        if user_message is not None and user_message.content != request.message:
            raise ConversationConflict(
                "idempotency_key was reused with different user content"
            )
        if user_message is not None:
            self._assert_request_binding(user_message, request)

        if user_message is None:
            thread, user_message = self._append_user(
                thread,
                request,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
        elif assistant_message is None:
            transcript = self.conversations.active_transcript(
                thread.thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
            if not transcript or transcript[-1].message_id != user_message.message_id:
                raise ConversationConflict(
                    "incomplete canonical turn is no longer the active tip"
                )

        request_id = _functional_request_id(
            thread.thread_id,
            user_message.message_id,
        )
        operation_id = _functional_operation_id(request_id)
        execution_id = _functional_execution_id(request_id)

        if assistant_message is not None:
            stored = self.functional_runtime.repository.result(execution_id)
            if stored is None:
                raise ConversationRepositoryCorruption(
                    "committed assistant message has no durable functional result"
                )
            current = self.functional_runtime.repository.get(execution_id)
            run = ExecutionRunResult(
                execution_id=execution_id,
                state=current.state,
                result=stored,
            )
            replay_request = FunctionalAIRequest(
                request_id=request_id,
                objective=(
                    "Respond to canonical conversation turn "
                    + user_message.message_id
                ),
                prompt=user_message.content or "canonical conversation turn",
                instructions=self.instruction_policy.instructions,
                context_digest=(
                    assistant_message.context_digest
                    if assistant_message.context_digest is not None
                    else self._missing_committed_context()
                ),
                allowed_tool_ids=request.allowed_tool_ids,
                data_class=thread.data_class,
                tenant_id=tenant_id,
                max_model_turns=request.max_model_turns,
                max_tool_calls=request.max_tool_calls,
                max_repeat_tool_batches=request.max_repeat_tool_batches,
                created_at=user_message.created_at,
            )
            if replay_request.execution_id != execution_id:
                raise CanonicalProductRuntimeError(
                    "functional execution identity derivation drifted"
                )
            evidence = self._materialize_evidence(replay_request, run)
            return self._response_from_committed(
                thread=thread,
                user_message=user_message,
                assistant_message=assistant_message,
                evidence=evidence,
                terminal=stored,
                replayed=True,
            )

        context = self._compile_context(
            thread=thread,
            user_message=user_message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            request=request,
            operation_id=operation_id,
            execution_id=execution_id,
        )
        projection = project_provider_context(context)
        if not projection.instructions.strip() or not projection.prompt.strip():
            raise CanonicalProductRuntimeError(
                "canonical context projection is missing instructions or prompt"
            )
        history = tuple(
            AIMessage(role=item["role"], content=item["content"])
            for item in projection.history
        )
        lower_request = FunctionalAIRequest(
            request_id=request_id,
            objective=(
                "Respond to canonical conversation turn "
                + user_message.message_id
            ),
            prompt=projection.prompt,
            instructions=projection.instructions,
            context_digest=context.context_digest,
            allowed_tool_ids=request.allowed_tool_ids,
            data_class=thread.data_class,
            tenant_id=tenant_id,
            max_model_turns=request.max_model_turns,
            max_tool_calls=request.max_tool_calls,
            max_repeat_tool_batches=request.max_repeat_tool_batches,
            created_at=user_message.created_at,
        )
        if (
            lower_request.operation_id != operation_id
            or lower_request.execution_id != execution_id
        ):
            raise CanonicalProductRuntimeError(
                "functional request identity derivation drifted"
            )

        run = await self._run_or_join_execution(
            execution_id=execution_id,
            request=lower_request.to_execution_request(),
            instructions=projection.instructions,
            prompt=projection.prompt,
            context_digest=context.context_digest,
            history=history,
            approval_refs=dict(request.approval_refs),
            now=user_message.created_at,
        )
        evidence = self._materialize_evidence(lower_request, run)
        terminal = run.result
        assert terminal is not None

        ai_result_id = "functional-ai-result:" + evidence.result_digest
        assistant_id = str(
            uuid5(
                NAMESPACE_URL,
                "skeleton-canonical-product-assistant:"
                + thread.thread_id
                + ":"
                + user_message.message_id,
            )
        )
        assistant = ConversationMessage(
            message_id=assistant_id,
            thread_id=thread.thread_id,
            branch_id=user_message.branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=terminal.completed_at,
            idempotency_key=request.idempotency_key + ":assistant",
            content=terminal.final_output,
            parent_message_id=user_message.message_id,
            causal_user_message_id=user_message.message_id,
            operation_id=lower_request.operation_id,
            ai_result_id=ai_result_id,
            context_id=context.context_id,
            context_digest=context.context_digest,
            context_source_snapshot=context.source_snapshot,
            context_compiler_version=context.compiler_version,
            tool_receipt_refs=terminal.tool_receipts,
            provider_receipt_refs=terminal.provider_receipts,
            memory_refs=terminal.memory_refs,
            citation_refs=terminal.evidence_refs,
            artifact_refs=terminal.artifact_refs,
            data_class=thread.data_class,
        )
        committed_thread, committed_assistant = self.conversations.append_message(
            assistant,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=thread.version,
        )
        return self._response_from_committed(
            thread=committed_thread,
            user_message=user_message,
            assistant_message=committed_assistant,
            evidence=evidence,
            terminal=terminal,
            replayed=False,
        )


    def _commit_cancel_marker(
        self,
        *,
        thread_id: str,
        tenant_id: str,
        owner_id: str,
        user_message: ConversationMessage,
        idempotency_key: str,
        operation_id: str,
        terminal,
        now: datetime,
    ) -> ConversationMessage:
        thread = self.conversations.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        _, existing_assistant = self._find_messages(
            thread,
            tenant_id=tenant_id,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
        )
        if existing_assistant is not None:
            raise ConversationConflict(
                "assistant response committed while cancellation was finalizing"
            )

        cancel_key = idempotency_key + ":cancelled"
        recent = self.conversations.list_messages(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            after_sequence=max(0, thread.message_sequence - 499),
            limit=500,
        )
        existing = next(
            (
                item
                for item in recent
                if item.author_type is ConversationAuthorType.SYSTEM_DERIVED
                and item.idempotency_key == cancel_key
            ),
            None,
        )
        if existing is not None:
            return existing

        marker = ConversationMessage(
            message_id=str(
                uuid5(
                    NAMESPACE_URL,
                    "skeleton-canonical-product-cancel:"
                    + thread_id
                    + ":"
                    + user_message.message_id,
                )
            ),
            thread_id=thread_id,
            branch_id=user_message.branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.SYSTEM_DERIVED,
            created_at=now,
            idempotency_key=cancel_key,
            content="Execution cancelled before an assistant response was committed.",
            parent_message_id=user_message.message_id,
            operation_id=operation_id,
            ai_result_id="functional-ai-result:" + _json_digest(terminal.as_dict()),
            data_class=thread.data_class,
        )
        _updated, committed = self.conversations.append_message(
            marker,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=thread.version,
        )
        return committed

    async def cancel_turn(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> ExecutionRunResult:
        """Durably cancel one canonical turn and interrupt local inference.

        The durable cancellation bit is written before the process-local task is
        interrupted.  A subsequent runtime resume then materializes the terminal
        cancelled result, so restart/retry observes one authoritative outcome.
        """

        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        thread = self.conversations.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        user_message, _assistant = self._find_messages(
            thread,
            tenant_id=tenant_id,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
        )
        if user_message is None:
            raise CanonicalProductRuntimeError(
                "cannot cancel unknown canonical turn"
            )
        request_id = _functional_request_id(
            thread.thread_id,
            user_message.message_id,
        )
        execution_id = _functional_execution_id(request_id)
        try:
            current = self.functional_runtime.repository.get(execution_id)
        except Exception as exc:
            raise CanonicalProductRuntimeError(
                "canonical turn has no durable functional execution"
            ) from exc

        if current.terminal:
            return ExecutionRunResult(
                execution_id=execution_id,
                state=current.state,
                result=self.functional_runtime.repository.result(execution_id),
            )

        instant = _aware(now or datetime.now(timezone.utc))
        self.functional_runtime.repository.request_cancel(
            execution_id,
            expected_version=current.version,
            now=instant,
        )

        async with self._active_tasks_lock:
            task = self._active_tasks.get(execution_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        result = await self.functional_runtime.runtime.resume(
            execution_id,
            now=instant,
        )
        if result.result is None or result.result.status != "cancelled":
            raise CanonicalProductRuntimeError(
                "cancellation did not materialize a terminal cancelled result"
            )
        self._commit_cancel_marker(
            thread_id=thread.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            user_message=user_message,
            idempotency_key=idempotency_key,
            operation_id=result.result.operation_id,
            terminal=result.result,
            now=instant,
        )
        return result


__all__ = [
    "CANONICAL_PRODUCT_CONTEXT_BUDGET",
    "CanonicalAIResponseEnvelope",
    "CanonicalAITurnRequest",
    "CanonicalConversationAIRuntime",
    "CanonicalProductRuntimeError",
]
