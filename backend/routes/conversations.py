"""First-class server-authoritative conversation API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
import uuid
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from core.conversations import ConversationStorageUnavailable, conversation_authority
from routes.gameforge_auth import require_role
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationThreadState,
)
from skeleton.persistence.conversation_repository import (
    ConversationConflict,
    ConversationNotFound,
    encode_thread_cursor,
)


router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


def _identity(user: dict) -> tuple[str, str]:
    owner = str(user.get("email") or user.get("user_id") or "").strip()
    if not owner:
        raise HTTPException(status_code=401, detail="Authentication required")
    tenant = str(user.get("tenant_id") or "default").strip()
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant identity is unavailable")
    return tenant, owner


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ConversationNotFound):
        return HTTPException(status_code=404, detail="Conversation not found")
    if isinstance(exc, ConversationConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ConversationStorageUnavailable):
        return HTTPException(status_code=503, detail="Conversation storage is unavailable")
    if isinstance(exc, (ValueError, TypeError)):
        return HTTPException(status_code=422, detail="Conversation request is invalid")
    return HTTPException(status_code=500, detail="Conversation operation failed")


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)
    data_class: Literal["public", "internal", "confidential", "restricted"] = "confidential"


class AppendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str = Field(min_length=1, max_length=1024)
    expected_thread_version: int = Field(ge=1)
    parent_message_id: str | None = None
    attachment_refs: list[str] = Field(default_factory=list, max_length=256)
    data_class: Literal["public", "internal", "confidential", "restricted"] = "confidential"


class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str = Field(min_length=1, max_length=1024)
    expected_thread_version: int = Field(ge=1)


class ThreadStateRequest(BaseModel):
    state: Literal["active", "archived", "deleting"]
    expected_thread_version: int = Field(ge=1)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    expected_thread_version: int = Field(ge=1, strict=True)


class RegenerateMessageRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=1024)
    expected_thread_version: int = Field(ge=1)
    provider_id: str | None = Field(default=None, min_length=1, max_length=128)
    model_id: str | None = Field(default=None, min_length=1, max_length=256)
    max_output_tokens: int | None = Field(default=None, ge=1, le=16_384, strict=True)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    response_mode: Literal["wait", "deferred"] = "wait"

    @model_validator(mode="after")
    def selection_pair(self):
        if (self.provider_id is None) != (self.model_id is None):
            raise ValueError("provider and model must be selected together")
        for value in (self.idempotency_key, self.provider_id, self.model_id):
            if value is not None and value != value.strip():
                raise ValueError("regeneration identity must be normalized")
        return self


class CancelRegenerationRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=1024)
    reason: str = Field(default="user_cancelled", min_length=1, max_length=512)


class ResumeRegenerationRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=1024)
    response_mode: Literal["wait", "deferred"] = "deferred"


def _lineage_to_message(messages, message_id: str):
    by_id = {message.message_id: message for message in messages}
    current = by_id.get(str(message_id))
    if current is None:
        raise ConversationNotFound(str(message_id))
    lineage = []
    seen = set()
    while current is not None:
        if current.message_id in seen:
            raise ConversationConflict("conversation lineage contains a cycle")
        seen.add(current.message_id)
        lineage.append(current)
        current = (
            by_id.get(current.parent_message_id)
            if current.parent_message_id is not None
            else None
        )
    lineage.reverse()
    return tuple(lineage)


@router.post("")
async def create_conversation(
    body: CreateConversationRequest,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        thread = await conversation_authority.create_thread(
            tenant_id=tenant_id,
            owner_id=owner_id,
            title=body.title,
            data_class=body.data_class,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {"thread": thread.as_dict()}


@router.get("")
async def list_conversations(
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str, Query(max_length=200)] = "",
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        options = {
            "tenant_id": tenant_id,
            "owner_id": owner_id,
            "include_archived": include_archived,
            "limit": limit,
        }
        if q:
            options["search"] = q
        if cursor is not None:
            options["cursor"] = cursor
        threads = await conversation_authority.list_threads(**options)
    except Exception as exc:
        raise _translate(exc) from exc
    next_cursor = (
        encode_thread_cursor(threads[-1].updated_at, threads[-1].thread_id) if len(threads) == limit else None
    )
    return {
        "threads": [thread.as_dict() for thread in threads],
        "count": len(threads),
        "next_cursor": next_cursor,
    }


@router.patch("/{thread_id}")
async def rename_conversation(
    thread_id: str, body: RenameConversationRequest, user=Depends(require_role("viewer"))
):
    tenant_id, owner_id = _identity(user)
    try:
        thread = await conversation_authority.rename_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_version=body.expected_thread_version,
            title=body.title,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {"thread": thread.as_dict()}


@router.get("/{thread_id}/snapshot")
async def get_conversation_snapshot(
    thread_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    before_message_id: Annotated[str | None, Query(max_length=64)] = None,
    expected_thread_version: Annotated[int | None, Query(ge=1)] = None,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        return dict(
            await conversation_authority.conversation_snapshot(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                limit=limit,
                before_message_id=before_message_id,
                expected_thread_version=expected_thread_version,
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/{thread_id}/recovery")
async def recover_conversation_snapshot(thread_id: str, user=Depends(require_role("viewer"))):
    """Reconstruct committed state; existing chat turn API owns engine resume/status."""
    tenant_id, owner_id = _identity(user)
    try:
        return dict(
            await conversation_authority.conversation_snapshot(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/{thread_id}/export")
async def export_conversation(
    thread_id: str,
    format: Literal["json", "markdown"] = "json",
    expected_thread_version: Annotated[int | None, Query(ge=1)] = None,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        return dict(
            await conversation_authority.export_thread(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                format=format,
                expected_thread_version=expected_thread_version,
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/{thread_id}")
async def get_conversation(
    thread_id: str,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        thread = await conversation_authority.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {"thread": thread.as_dict()}


@router.post("/{thread_id}/messages")
async def append_user_message(
    thread_id: str,
    body: AppendMessageRequest,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        thread, message = await conversation_authority.append_user_message(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            content=body.content,
            idempotency_key=body.idempotency_key,
            expected_thread_version=body.expected_thread_version,
            parent_message_id=body.parent_message_id,
            attachment_refs=tuple(body.attachment_refs),
            data_class=body.data_class,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {"thread": thread.as_dict(), "message": message.as_dict()}


@router.get("/{thread_id}/messages")
async def get_messages(
    thread_id: str,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    active_only: bool = False,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        if active_only:
            messages = await conversation_authority.active_transcript(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
            if after_sequence:
                messages = tuple(
                    message
                    for message in messages
                    if message.sequence > after_sequence
                )
            messages = messages[:limit]
        else:
            messages = await conversation_authority.list_messages(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                after_sequence=after_sequence,
                limit=limit,
            )
    except Exception as exc:
        raise _translate(exc) from exc
    next_after = messages[-1].sequence if len(messages) == limit else None
    return {
        "thread_id": thread_id,
        "messages": [message.as_dict() for message in messages],
        "count": len(messages),
        "next_after_sequence": next_after,
        "projection": "active" if active_only else "all",
    }


def _regeneration_digest(body: RegenerateMessageRequest) -> str:
    data = {
        "idempotency_key": body.idempotency_key,
        "provider_id": body.provider_id,
        "model_id": body.model_id,
        "max_output_tokens": body.max_output_tokens,
        "temperature": body.temperature,
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _regeneration_command(record, tenant_id, owner_id):
    from skeleton.api.engine_service import EngineExecutionCommand, EngineServiceError

    try:
        command = EngineExecutionCommand.from_dict(record["command"])
        if (
            command.operation.actor_id != owner_id
            or command.operation.tenant_id != tenant_id
            or command.compiled_context.turn_id != record["causal_user_message_id"]
            or command.compiled_context.tenant_id != tenant_id
            or command.operation.idempotency_key != record["idempotency_key"]
        ):
            raise ValueError("regeneration actor/tenant/causal identity drift")
        expected_operation = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "skeleton-conversation-regenerate:"
                + record["thread_id"]
                + ":"
                + record["message_id"]
                + ":"
                + record["idempotency_key"],
            )
        )
        expected_execution = str(
            uuid.uuid5(uuid.NAMESPACE_URL, "skeleton-conversation-regenerate-execution:" + expected_operation)
        )
        if (
            command.operation.operation_id != expected_operation
            or command.execution_request.execution_id != expected_execution
        ):
            raise ValueError("regeneration execution identity drift")
        return command
    except (ValueError, TypeError, KeyError, EngineServiceError) as exc:
        raise ConversationStorageUnavailable("Stored regeneration request is malformed") from exc


async def _project_regeneration(record, *, tenant_id, owner_id, engine):
    from core.engine_client import EngineExecutionFailed, EngineNotFoundError

    command = _regeneration_command(record, tenant_id, owner_id)
    operation_id = command.operation.operation_id
    execution_id = command.execution_request.execution_id
    thread = await conversation_authority.get_thread(
        record["thread_id"], tenant_id=tenant_id, owner_id=owner_id
    )
    existing = await conversation_authority.assistant_message_for_operation(
        operation_id, tenant_id=tenant_id, owner_id=owner_id
    )
    base = {
        "operation_id": operation_id,
        "engine_execution_id": execution_id,
        "idempotency_key": record["idempotency_key"],
        "regenerated_from": record["message_id"],
        "causal_user_message_id": record["causal_user_message_id"],
        "thread": thread.as_dict(),
    }
    if existing is not None:
        if existing.thread_id != thread.thread_id or existing.supersedes_message_id != record["message_id"]:
            raise ConversationStorageUnavailable("Regeneration result lineage mismatch")
        return {
            **base,
            "success": True,
            "terminal": True,
            "state": "completed",
            "replayed": True,
            "message": existing.as_dict(),
            "assistant_message": existing.as_dict(),
            "response": existing.content,
            "ai_result_id": existing.ai_result_id,
        }
    dispatch = await conversation_authority.regeneration_dispatch_state(
        record, tenant_id=tenant_id, owner_id=owner_id
    )
    if dispatch["state"] == "withdrawn":
        return {
            **base,
            "success": False,
            "accepted": False,
            "terminal": True,
            "state": "withdrawn",
            "cancellation_requested": True,
            "failure_code": "user_cancelled_before_admission",
            "response": None,
            "ai_generated": False,
        }
    try:
        result = await engine.terminal_result_if_available(
            execution_id=execution_id,
            actor_id=owner_id,
            tenant_id=tenant_id,
            trace_id=command.operation.trace_id,
        )
    except EngineExecutionFailed as exc:
        return {
            **base,
            "success": False,
            "terminal": True,
            "state": exc.status,
            "failure_code": exc.failure_code,
            "response": None,
            "ai_generated": False,
        }
    except EngineNotFoundError:
        return {
            **base,
            "success": False,
            "accepted": False,
            "terminal": False,
            "state": "cancellation_requested" if dispatch["cancel_requested"] else "awaiting_admission",
            "cancellation_requested": dispatch["cancel_requested"],
            "response": None,
            "ai_generated": False,
        }
    if result is None:
        if dispatch["cancel_requested"]:
            await engine.cancel(
                execution_id,
                actor_id=owner_id,
                tenant_id=tenant_id,
                reason="user_cancelled",
                trace_id=command.operation.trace_id,
            )
        status = await engine.status(
            execution_id, actor_id=owner_id, tenant_id=tenant_id, trace_id=command.operation.trace_id
        )
        return {
            **base,
            "success": True,
            "accepted": True,
            "terminal": False,
            "state": status.get("execution_state", "running"),
            "cancellation_requested": dispatch["cancel_requested"]
            or bool(status.get("cancellation_requested", False)),
            "response": None,
        }
    if result.execution_id != execution_id:
        raise ConversationStorageUnavailable("Regeneration engine result identity mismatch")
    if (
        not thread.writable
        or thread.message_sequence != record["initial_message_sequence"]
        or thread.active_branch_id != record["initial_active_branch_id"]
    ):
        return {
            **base,
            "success": False,
            "terminal": True,
            "state": "conversation_conflict",
            "failure_code": "regeneration_lineage_changed",
            "response": None,
            "ai_generated": False,
        }
    handoff = command.compiled_context
    try:
        thread, message = await conversation_authority.regenerate_assistant_message(
            thread.thread_id,
            record["message_id"],
            tenant_id=tenant_id,
            owner_id=owner_id,
            content=result.final_output,
            idempotency_key=record["idempotency_key"],
            expected_thread_version=thread.version,
            operation_id=operation_id,
            ai_result_id="engine-result:" + execution_id,
            context_id=handoff.context_id,
            context_digest=handoff.context_digest,
            context_source_snapshot=handoff.source_snapshot,
            context_compiler_version=handoff.compiler_version,
            tool_receipt_refs=tuple(getattr(result, "tool_receipts", ())),
            provider_receipt_refs=tuple(getattr(result, "provider_receipts", ())),
            memory_refs=tuple(getattr(result, "memory_refs", ())),
            citation_refs=tuple(getattr(result, "evidence_refs", ())),
            artifact_refs=tuple(getattr(result, "artifact_refs", ())),
        )
    except ConversationConflict:
        existing = await conversation_authority.assistant_message_for_operation(
            operation_id, tenant_id=tenant_id, owner_id=owner_id
        )
        if existing is None:
            raise
        message = existing
        thread = await conversation_authority.get_thread(
            record["thread_id"], tenant_id=tenant_id, owner_id=owner_id
        )
    return {
        **base,
        "success": True,
        "accepted": True,
        "terminal": True,
        "state": "completed",
        "thread": thread.as_dict(),
        "message": message.as_dict(),
        "assistant_message": message.as_dict(),
        "response": message.content,
        "ai_generated": True,
        "ai_result_id": message.ai_result_id,
        "verification": result.verification,
        "evidence_refs": list(result.evidence_refs),
    }


async def _submit_regeneration(record, command, *, tenant_id, owner_id, engine):
    current = await conversation_authority.authorize_active_thread(
        record["thread_id"], tenant_id=tenant_id, owner_id=owner_id
    )
    if (
        current.message_sequence != record["initial_message_sequence"]
        or current.active_branch_id != record["initial_active_branch_id"]
    ):
        raise ConversationConflict("thread lineage changed before regeneration dispatch")
    dispatch = await conversation_authority.transition_regeneration_dispatch(
        record, tenant_id=tenant_id, owner_id=owner_id
    )
    if dispatch["state"] == "withdrawn" or dispatch["cancel_requested"]:
        return
    if dispatch["state"] == "admitted":
        raise ConversationStorageUnavailable("the engine cannot resolve the already admitted regeneration")
    acknowledgement = await engine.submit(command)
    engine._validate_ack_identity(acknowledgement, command)
    await conversation_authority.transition_regeneration_dispatch(
        record, tenant_id=tenant_id, owner_id=owner_id, admitted=True
    )


@router.post("/{thread_id}/messages/{message_id}/regenerate")
async def regenerate_assistant_message(
    thread_id: str, message_id: str, body: RegenerateMessageRequest, user=Depends(require_role("viewer"))
):
    """Persist one exact regeneration request before submitting canonical engine work."""
    from core.engine_client import EngineClientError, EngineExecutionFailed, command_from_context
    from core.model_catalog import (
        ModelSelectionError,
        model_catalog,
        resolve_selection,
        context_budget_for_selection,
    )
    from core.chat_attachments import resolve_attachment_context
    from routes.ai import (
        CHAT_INSTRUCTION_POLICY,
        _compile_chat_context,
        _provider_history,
        _chat_engine,
        _engine_chat_error,
    )

    tenant_id, owner_id = _identity(user)
    engine = _chat_engine()
    try:
        record = await conversation_authority.regeneration_request(
            thread_id, message_id, body.idempotency_key, tenant_id=tenant_id, owner_id=owner_id
        )
        semantic_digest = _regeneration_digest(body)
        if record is not None:
            if record["request_digest"] != semantic_digest:
                raise ConversationConflict("regeneration key was reused with different settings")
        else:
            thread = await conversation_authority.authorize_active_thread(
                thread_id, tenant_id=tenant_id, owner_id=owner_id
            )
            if thread.version != body.expected_thread_version:
                raise ConversationConflict("thread version conflict")
            messages = await conversation_authority.active_transcript(
                thread_id, tenant_id=tenant_id, owner_id=owner_id
            )
            target = next((message for message in messages if message.message_id == message_id), None)
            if target is None:
                raise ConversationNotFound(message_id)
            if (
                target.author_type is not ConversationAuthorType.ASSISTANT
                or target.causal_user_message_id is None
            ):
                raise ConversationConflict("only causal assistant messages can be regenerated")
            causal = next(
                (message for message in messages if message.message_id == target.causal_user_message_id), None
            )
            if causal is None or causal.author_type is not ConversationAuthorType.USER:
                raise ConversationConflict("assistant causal user message is unavailable")
            lineage = _lineage_to_message(messages, causal.message_id)
            operation_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "skeleton-conversation-regenerate:"
                    + thread_id
                    + ":"
                    + message_id
                    + ":"
                    + body.idempotency_key,
                )
            )
            execution_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, "skeleton-conversation-regenerate-execution:" + operation_id)
            )
            catalog = await model_catalog(engine, actor_id=owner_id, tenant_id=tenant_id)
            selection = resolve_selection(catalog, provider_id=body.provider_id, model_id=body.model_id)
            budget = context_budget_for_selection(selection, output_tokens=body.max_output_tokens)
            if body.temperature is not None and selection.get("supports_temperature") is not True:
                raise ModelSelectionError("model_temperature_unsupported")
            attachment_refs = tuple(
                ref for ref in causal.attachment_refs if ref.startswith("chat-attachment://")
            )
            attachments = await resolve_attachment_context(
                thread_id=thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                attachment_refs=attachment_refs,
                created_at=causal.created_at,
            )
            context = _compile_chat_context(
                thread=thread,
                transcript=lineage,
                user_message=causal,
                tenant_id=tenant_id,
                operation_id=operation_id,
                execution_id=execution_id,
                request_context=None,
                budget=budget,
                attachment_segments=attachments.segments,
            )
            started = datetime.now(timezone.utc)
            command = command_from_context(
                context=context,
                actor_id=owner_id,
                capability="assistant.chat",
                idempotency_key=body.idempotency_key,
                instructions=CHAT_INSTRUCTION_POLICY.instructions,
                prompt=causal.content or "",
                objective="Regenerate canonical assistant response for " + causal.message_id,
                verification_profile="assistant_proposal",
                history=_provider_history(lineage, exclude_message_id=causal.message_id),
                service_principal=engine.config.service_principal,
                created_at=started,
                deadline=started + timedelta(seconds=engine.config.execution_timeout_s),
                trace_id="conversation-regenerate:" + operation_id,
                max_model_turns=4,
                max_tool_calls=1,
                max_repeat_tool_batches=1,
                max_output_tokens=budget.reserved_output_tokens,
                provider_id=selection["selection_provider_id"],
                model_id=selection["selection_model_id"],
                temperature=body.temperature,
                context_seed_refs=(
                    "conversation:" + thread_id,
                    "conversation-message:" + causal.message_id,
                    "supersedes-assistant:" + message_id,
                ),
            )
            record = {
                "schema_version": "skeleton.conversation.regeneration_request.v1",
                "thread_id": thread_id,
                "message_id": message_id,
                "causal_user_message_id": causal.message_id,
                "idempotency_key": body.idempotency_key,
                "request_digest": semantic_digest,
                "initial_thread_version": thread.version,
                "initial_message_sequence": thread.message_sequence,
                "initial_active_branch_id": thread.active_branch_id,
                "command": command.as_dict(),
            }
            record["record_digest"] = hashlib.sha256(
                json.dumps(
                    record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
                ).encode()
            ).hexdigest()
            record = await conversation_authority.bind_regeneration_request(
                thread_id,
                message_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                expected_thread_version=body.expected_thread_version,
                record=record,
            )
        command = _regeneration_command(record, tenant_id, owner_id)
        projected = await _project_regeneration(record, tenant_id=tenant_id, owner_id=owner_id, engine=engine)
        if projected.get("terminal") or projected.get("state") == "cancellation_requested":
            return projected
        if projected.get("state") == "awaiting_admission":
            await _submit_regeneration(record, command, tenant_id=tenant_id, owner_id=owner_id, engine=engine)
        if body.response_mode == "wait":
            try:
                await engine.wait_for_terminal(
                    execution_id=command.execution_request.execution_id,
                    actor_id=owner_id,
                    tenant_id=tenant_id,
                    trace_id=command.operation.trace_id,
                )
            except EngineExecutionFailed:
                pass
        return await _project_regeneration(record, tenant_id=tenant_id, owner_id=owner_id, engine=engine)
    except HTTPException:
        raise
    except ModelSelectionError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "message": "Selected model is unavailable"}
        ) from exc
    except EngineClientError as exc:
        raise _engine_chat_error(exc) from exc
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/{thread_id}/messages/{message_id}/regenerate/turn")
async def get_regeneration_turn(
    thread_id: str,
    message_id: str,
    idempotency_key: Annotated[str, Query(min_length=1, max_length=1024)],
    user=Depends(require_role("viewer")),
):
    from core.engine_client import EngineClientError
    from routes.ai import _chat_engine, _engine_chat_error

    tenant_id, owner_id = _identity(user)
    try:
        record = await conversation_authority.regeneration_request(
            thread_id, message_id, idempotency_key, tenant_id=tenant_id, owner_id=owner_id
        )
        if record is None:
            raise ConversationNotFound(message_id)
        return await _project_regeneration(
            record, tenant_id=tenant_id, owner_id=owner_id, engine=_chat_engine()
        )
    except HTTPException:
        raise
    except EngineClientError as exc:
        raise _engine_chat_error(exc) from exc
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/{thread_id}/messages/{message_id}/regenerate/cancel")
async def cancel_regeneration_turn(
    thread_id: str, message_id: str, body: CancelRegenerationRequest, user=Depends(require_role("viewer"))
):
    from core.engine_client import EngineClientError
    from routes.ai import _chat_engine, _engine_chat_error

    tenant_id, owner_id = _identity(user)
    try:
        record = await conversation_authority.regeneration_request(
            thread_id, message_id, body.idempotency_key, tenant_id=tenant_id, owner_id=owner_id
        )
        if record is None:
            raise ConversationNotFound(message_id)
        command = _regeneration_command(record, tenant_id, owner_id)
        engine = _chat_engine()
        projected = await _project_regeneration(record, tenant_id=tenant_id, owner_id=owner_id, engine=engine)
        if projected.get("terminal") or projected.get("state") == "cancellation_requested":
            return projected
        dispatch = await conversation_authority.transition_regeneration_dispatch(
            record, tenant_id=tenant_id, owner_id=owner_id, cancel=True
        )
        if dispatch["state"] != "withdrawn" and projected.get("state") != "awaiting_admission":
            await engine.cancel(
                command.execution_request.execution_id,
                actor_id=owner_id,
                tenant_id=tenant_id,
                reason=body.reason,
                trace_id=command.operation.trace_id,
            )
        result = await _project_regeneration(record, tenant_id=tenant_id, owner_id=owner_id, engine=engine)
        result["cancellation_requested"] = True
        return result
    except HTTPException:
        raise
    except EngineClientError as exc:
        raise _engine_chat_error(exc) from exc
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/{thread_id}/messages/{message_id}/regenerate/resume")
async def resume_regeneration_turn(
    thread_id: str,
    message_id: str,
    body: ResumeRegenerationRequest,
    user=Depends(require_role("viewer")),
):
    """Resume the persisted exact command; browser settings are never reconstructed."""
    from core.engine_client import EngineClientError, EngineExecutionFailed
    from routes.ai import _chat_engine, _engine_chat_error

    tenant_id, owner_id = _identity(user)
    try:
        record = await conversation_authority.regeneration_request(
            thread_id,
            message_id,
            body.idempotency_key,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if record is None:
            raise ConversationNotFound(message_id)
        engine = _chat_engine()
        command = _regeneration_command(record, tenant_id, owner_id)
        projected = await _project_regeneration(record, tenant_id=tenant_id, owner_id=owner_id, engine=engine)
        if projected.get("terminal") or projected.get("state") == "cancellation_requested":
            return projected
        if projected.get("state") == "awaiting_admission":
            await _submit_regeneration(record, command, tenant_id=tenant_id, owner_id=owner_id, engine=engine)
        if body.response_mode == "wait":
            try:
                await engine.wait_for_terminal(
                    execution_id=command.execution_request.execution_id,
                    actor_id=owner_id,
                    tenant_id=tenant_id,
                    trace_id=command.operation.trace_id,
                )
            except EngineExecutionFailed:
                pass
        return await _project_regeneration(record, tenant_id=tenant_id, owner_id=owner_id, engine=engine)
    except HTTPException:
        raise
    except EngineClientError as exc:
        raise _engine_chat_error(exc) from exc
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/{thread_id}/messages/{message_id}/edit")
async def edit_message(
    thread_id: str,
    message_id: str,
    body: EditMessageRequest,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        thread, message = await conversation_authority.edit_user_message(
            thread_id,
            message_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            content=body.content,
            idempotency_key=body.idempotency_key,
            expected_thread_version=body.expected_thread_version,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {"thread": thread.as_dict(), "message": message.as_dict()}


@router.patch("/{thread_id}/state")
async def update_thread_state(
    thread_id: str,
    body: ThreadStateRequest,
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        thread = await conversation_authority.set_state(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_version=body.expected_thread_version,
            state=ConversationThreadState(body.state),
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {"thread": thread.as_dict()}


@router.post("/retention/sweep")
async def sweep_conversation_retention(
    user=Depends(require_role("admin")),
):
    """Execute one tenant-scoped governed retention sweep."""

    tenant_id, _owner_id = _identity(user)
    try:
        result = await conversation_authority.execute_due_retention(
            tenant_id=tenant_id,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return dict(result)


@router.delete("/{thread_id}")
async def request_conversation_deletion(
    thread_id: str,
    expected_thread_version: Annotated[int, Query(ge=1)],
    user=Depends(require_role("viewer")),
):
    """Execute governed deletion across canonical conversation-linked state."""

    tenant_id, owner_id = _identity(user)
    try:
        result = await conversation_authority.delete_thread_with_governance(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "thread": result["thread"],
        "deletion_state": "deleted",
        "complete": True,
        "plan_id": result["plan_id"],
        "record_ids": result["record_ids"],
        "linked_execution": result["linked_execution"],
    }
