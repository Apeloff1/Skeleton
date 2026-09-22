"""First-class server-authoritative conversation API."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.conversations import ConversationStorageUnavailable, conversation_authority
from routes.gameforge_auth import require_role
from skeleton.contracts.conversation import ConversationThreadState
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
