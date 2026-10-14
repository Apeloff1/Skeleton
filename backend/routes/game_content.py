"""Authenticated streamed large ROM/disc uploads for game learning."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Path, Request as HTTPRequest
from pydantic import Field

from core.game_content_uploads import CHUNK_BYTES, content_uploads
from routes.game_learning import Request, User, WriteRequest, _call, _scope

router = APIRouter(prefix="/game-learning", tags=["Game media"])


class ContentFile(Request):
    path: str = Field(min_length=1, max_length=256)
    bytes: int = Field(ge=1, le=2 * 1024**3, strict=True)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ContentUpload(WriteRequest):
    files: list[ContentFile] = Field(min_length=1, max_length=64)
    entrypoint: str = Field(min_length=1, max_length=256)
    rights_refs: list[str] = Field(min_length=1, max_length=64)
    rights_acknowledged: bool = False


@router.post("/projects/{project_id}/content-uploads")
async def create_upload(project_id: str, body: ContentUpload, user: User):
    return {"upload": await _call(content_uploads.create(_scope(user), project_id, body.model_dump(exclude_none=True)))}


@router.get("/content-uploads/{upload_id}")
async def upload_status(upload_id: str, user: User):
    return {"upload": await _call(content_uploads.status(_scope(user), upload_id))}


@router.put("/content-uploads/{upload_id}/files/{file_index}/chunks/{chunk_index}")
async def upload_chunk(
    upload_id: str,
    file_index: Annotated[int, Path(ge=0, le=63)],
    chunk_index: Annotated[int, Path(ge=0, le=2047)],
    request: HTTPRequest,
    user: User,
    chunk_hash: Annotated[str, Header(alias="X-Chunk-SHA256", pattern=r"^[0-9a-f]{64}$")],
):
    scope = _scope(user)
    declared_length = request.headers.get("content-length")
    if declared_length is not None and (not declared_length.isdigit() or not 1 <= int(declared_length) <= CHUNK_BYTES):
        raise HTTPException(413, detail={"code": "content_chunk_size", "message": "Chunks may contain at most 1 MiB."})
    # Reject foreign/closed uploads before consuming an untrusted request body.
    await _call(content_uploads._read(scope, upload_id))
    buffer = bytearray()
    async for chunk in request.stream():
        if len(buffer) + len(chunk) > CHUNK_BYTES:
            raise HTTPException(
                413, detail={"code": "content_chunk_size", "message": "Chunks may contain at most 1 MiB."}
            )
        buffer.extend(chunk)
    return {
        "upload": await _call(
            content_uploads.put_chunk(scope, upload_id, file_index, chunk_index, bytes(buffer), chunk_hash)
        )
    }


@router.post("/content-uploads/{upload_id}/complete")
async def complete_upload(upload_id: str, user: User):
    return await _call(content_uploads.complete(_scope(user), upload_id))


@router.delete("/content-uploads/{upload_id}")
async def withdraw_upload(upload_id: str, user: User):
    return {"upload": await _call(content_uploads.withdraw(_scope(user), upload_id))}
