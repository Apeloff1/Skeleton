"""Authenticated conversation file upload and current reference lifecycle."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pymongo.errors import PyMongoError

from core.chat_attachments import (
    MAX_BASE64_CHARS,
    ChatAttachmentError,
    attachment_capabilities,
    delete_attachment,
    get_attachment,
    upload_attachment,
)
from core.conversations import ConversationStorageUnavailable
from routes.gameforge_auth import require_role
from skeleton.persistence.conversation_repository import ConversationConflict, ConversationNotFound

router = APIRouter(prefix="/ai/attachments", tags=["Chat attachments"])
MAX_REQUEST_BYTES = MAX_BASE64_CHARS + 16 * 1024


class UploadAttachmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    thread_id: str = Field(min_length=1, max_length=512)
    filename: str = Field(min_length=1, max_length=512)
    media_type: str = Field(min_length=1, max_length=128)
    base64: str = Field(min_length=1, max_length=MAX_BASE64_CHARS)
    rights_acknowledged: Literal[True]
    upload_id: str | None = Field(default=None, max_length=64)


def _identity(user: dict) -> tuple[str, str]:
    owner = str(user.get("email") or user.get("user_id") or "").strip()
    tenant = str(user.get("tenant_id") or "default").strip()
    if not owner:
        raise HTTPException(401, "Authentication required")
    if not tenant:
        raise HTTPException(403, "Tenant identity is unavailable")
    return tenant, owner


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ChatAttachmentError):
        return HTTPException(exc.status_code, str(exc))
    if isinstance(exc, ConversationNotFound):
        return HTTPException(404, "Conversation not found")
    if isinstance(exc, ConversationConflict):
        return HTTPException(409, str(exc))
    if isinstance(exc, (ConversationStorageUnavailable, PyMongoError)):
        return HTTPException(503, "Attachment storage is unavailable")
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return HTTPException(422, "Attachment request is invalid")
    return HTTPException(503, "Attachment operation could not be completed")


def _unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate request key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("nonfinite request number")


@router.get("/capabilities")
async def file_capabilities(user=Depends(require_role("viewer"))):
    _identity(user)
    return attachment_capabilities()


@router.post("")
async def upload_file(request: Request, user=Depends(require_role("viewer"))):
    tenant_id, owner_id = _identity(user)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(415, "Upload a JSON file envelope")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Attachments must be smaller than 5 MB")
        data.extend(chunk)
    try:
        raw = json.loads(bytes(data), object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
        body = UploadAttachmentRequest.model_validate(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError) as exc:
        raise HTTPException(422, "Attachment upload envelope is invalid") from exc
    try:
        return await upload_attachment(
            thread_id=body.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            filename=body.filename,
            media_type=body.media_type,
            encoded=body.base64,
            rights_acknowledged=body.rights_acknowledged,
            upload_id=body.upload_id,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/{attachment_id}")
async def attachment_metadata(
    attachment_id: str,
    thread_id: str = Query(min_length=1, max_length=512),
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        return await get_attachment(
            attachment_id, thread_id=thread_id, tenant_id=tenant_id, owner_id=owner_id
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.delete("/{attachment_id}")
async def remove_attachment(
    attachment_id: str,
    thread_id: str = Query(min_length=1, max_length=512),
    user=Depends(require_role("viewer")),
):
    tenant_id, owner_id = _identity(user)
    try:
        return await delete_attachment(
            attachment_id, thread_id=thread_id, tenant_id=tenant_id, owner_id=owner_id
        )
    except Exception as exc:
        raise _translate(exc) from exc
