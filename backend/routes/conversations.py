"""First-class server-authoritative conversation API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.conversations import ConversationStorageUnavailable, conversation_authority
from routes.gameforge_auth import require_role
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationThreadState,
)
from skeleton.persistence.conversation_repository import (
    ConversationConflict,
    ConversationNotFound,
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


class RegenerateMessageRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=1024)
    expected_thread_version: int = Field(ge=1)


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
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        threads = await conversation_authority.list_threads(
            tenant_id=tenant_id,
            owner_id=owner_id,
            include_archived=include_archived,
            limit=limit,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {"threads": [thread.as_dict() for thread in threads], "count": len(threads)}


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


@router.post("/{thread_id}/messages/{message_id}/regenerate")
async def regenerate_assistant_message(
    thread_id: str,
    message_id: str,
    body: RegenerateMessageRequest,
    user=Depends(require_role("viewer")),
):
    """Regenerate one assistant message through a new canonical engine result."""

    from core.engine_client import (
        EngineClient,
        EngineClientError,
        EngineExecutionFailed,
        EngineUnavailableError,
        command_from_context,
    )
    from routes.ai import (
        CHAT_INSTRUCTION_POLICY,
        _compile_chat_context,
        _provider_history,
    )

    tenant_id, owner_id = _identity(user)
    try:
        thread = await conversation_authority.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if thread.version != body.expected_thread_version:
            raise ConversationConflict("thread version conflict")
        messages = await conversation_authority.list_messages(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            limit=500,
        )
        target = next(
            (
                message
                for message in messages
                if message.message_id == message_id
            ),
            None,
        )
        if target is None:
            raise ConversationNotFound(message_id)
        if target.author_type is not ConversationAuthorType.ASSISTANT:
            raise ConversationConflict(
                "only assistant messages can be regenerated"
            )
        causal_id = target.causal_user_message_id
        if causal_id is None:
            raise ConversationConflict(
                "assistant message is missing causal user lineage"
            )
        causal = next(
            (
                message
                for message in messages
                if message.message_id == causal_id
            ),
            None,
        )
        if (
            causal is None
            or causal.author_type is not ConversationAuthorType.USER
        ):
            raise ConversationConflict(
                "assistant causal user message is unavailable"
            )
        lineage = _lineage_to_message(messages, causal.message_id)
    except Exception as exc:
        raise _translate(exc) from exc

    operation_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                "skeleton-conversation-regenerate:"
                + thread.thread_id
                + ":"
                + target.message_id
                + ":"
                + body.idempotency_key
            ),
        )
    )
    execution_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "skeleton-conversation-regenerate-execution:" + operation_id,
        )
    )
    context = _compile_chat_context(
        thread=thread,
        transcript=lineage,
        user_message=causal,
        tenant_id=tenant_id,
        operation_id=operation_id,
        execution_id=execution_id,
        request_context=None,
    )
    history = _provider_history(
        lineage,
        exclude_message_id=causal.message_id,
    )

    try:
        engine = EngineClient.from_env()
    except EngineClientError as exc:
        raise HTTPException(
            status_code=503,
            detail="AI engine configuration is unavailable",
        ) from exc
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="AI engine is unavailable",
        )

    started = datetime.now(timezone.utc)
    try:
        command = command_from_context(
            context=context,
            actor_id=owner_id,
            capability="assistant.chat",
            idempotency_key=body.idempotency_key,
            instructions=CHAT_INSTRUCTION_POLICY.instructions,
            prompt=causal.content or "",
            objective=(
                "Regenerate canonical assistant response for "
                + causal.message_id
            ),
            verification_profile="assistant_proposal",
            history=history,
            service_principal=engine.config.service_principal,
            created_at=started,
            deadline=started
            + timedelta(seconds=engine.config.execution_timeout_s),
            trace_id="conversation-regenerate:" + operation_id,
            max_model_turns=4,
            max_tool_calls=1,
            max_repeat_tool_batches=1,
            context_seed_refs=(
                "conversation:" + thread.thread_id,
                "conversation-message:" + causal.message_id,
                "supersedes-assistant:" + target.message_id,
            ),
        )
        result = await engine.execute(command)
    except EngineUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="AI engine is unavailable",
        ) from exc
    except EngineExecutionFailed as exc:
        raise HTTPException(
            status_code=502,
            detail="AI regeneration failed",
        ) from exc
    except EngineClientError as exc:
        raise HTTPException(
            status_code=502,
            detail="AI regeneration request failed",
        ) from exc

    try:
        committed_thread, regenerated = (
            await conversation_authority.regenerate_assistant_message(
                thread_id,
                target.message_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                content=result.final_output,
                idempotency_key=body.idempotency_key,
                expected_thread_version=body.expected_thread_version,
                operation_id=operation_id,
                ai_result_id="engine-result:" + result.execution_id,
                context_id=context.context_id,
                context_digest=context.context_digest,
                context_source_snapshot=context.source_snapshot,
                context_compiler_version=context.compiler_version,
                tool_receipt_refs=tuple(
                    getattr(result, "tool_receipts", ())
                ),
                memory_refs=tuple(
                    getattr(result, "memory_refs", ())
                ),
                citation_refs=tuple(
                    getattr(result, "evidence_refs", ())
                ),
                artifact_refs=tuple(
                    getattr(result, "artifact_refs", ())
                ),
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc

    return {
        "thread": committed_thread.as_dict(),
        "message": regenerated.as_dict(),
        "regenerated_from": target.message_id,
        "causal_user_message_id": causal.message_id,
        "operation_id": operation_id,
        "engine_execution_id": result.execution_id,
        "ai_result_id": "engine-result:" + result.execution_id,
        "verification": result.verification,
        "evidence_refs": list(result.evidence_refs),
        "tool_receipt_refs": list(
            getattr(result, "tool_receipts", ())
        ),
        "memory_refs": list(
            getattr(result, "memory_refs", ())
        ),
        "artifact_refs": list(
            getattr(result, "artifact_refs", ())
        ),
    }


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


@router.delete("/{thread_id}")
async def request_conversation_deletion(
    thread_id: str,
    expected_thread_version: Annotated[int, Query(ge=1)],
    user=Depends(require_role("viewer")),
):
    """Enter deletion lifecycle without claiming downstream propagation is done."""

    tenant_id, owner_id = _identity(user)
    try:
        thread = await conversation_authority.set_state(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_version=expected_thread_version,
            state=ConversationThreadState.DELETING,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "thread": thread.as_dict(),
        "deletion_state": "deleting",
        "complete": False,
        "detail": "Conversation deletion propagation is queued for governance lifecycle handling.",
    }
