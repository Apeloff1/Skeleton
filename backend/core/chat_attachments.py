"""Conversation-scoped uploads projected into canonical untrusted context.

Original bytes and extracted evidence remain in the existing core database.
Neither a file reference nor extracted text grants instruction or tool authority.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import importlib.util
import io
import json
import multiprocessing
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from pymongo import ReturnDocument

from skeleton.context.sources import artifact_segment
from skeleton.contracts.context import ContextSegment

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_BASE64_CHARS = 4 * ((MAX_ATTACHMENT_BYTES + 2) // 3)
MAX_EXTRACTED_BYTES = 48 * 1024
MAX_CONTEXT_BYTES = 128 * 1024
MAX_REFS = 4
MAX_OWNER_BYTES = 50 * 1024 * 1024
MAX_OWNER_FILES = 128
MAX_THREAD_FILES = 32
RETENTION_SECONDS = 24 * 60 * 60
EXTRACTOR_VERSION = "chat-file-extraction@1"
ATTACHMENT_PREFIX = "chat-attachment://"
_TEXT_MIMES = frozenset({"text/plain", "text/markdown", "text/csv", "application/json"})
_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})
_ALL_MIMES = _TEXT_MIMES | _IMAGE_MIMES | {"application/pdf", "audio/wav"}
_UPLOAD_SLOTS = asyncio.Semaphore(2)
_INDEX_LOCK = asyncio.Lock()
_INDEX_READY = False


class ChatAttachmentError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.status_code = status_code


def _now() -> datetime:
    instant = datetime.now(timezone.utc)
    # BSON preserves milliseconds; immutable wire timestamps use that precision.
    return instant.replace(microsecond=(instant.microsecond // 1000) * 1000)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ChatAttachmentError("Attachment timestamps are corrupt", 503)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _text(value: object, label: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > maximum:
        raise ChatAttachmentError(f"{label} is missing or too long")
    return value.strip()


def _attachment_id(value: str) -> str:
    raw = value.removeprefix(ATTACHMENT_PREFIX)
    try:
        identifier = str(UUID(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ChatAttachmentError("Attachment reference is invalid") from exc
    if identifier != raw:
        raise ChatAttachmentError("Attachment reference must be a canonical UUID")
    return identifier


def safe_filename(value: str) -> str:
    name = _text(value, "Filename", 512)
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).lstrip(".")[:100] or "attachment"


def attachment_capabilities() -> dict:
    process_bounds = importlib.util.find_spec("resource") is not None
    pdf = process_bounds and importlib.util.find_spec("pypdf") is not None
    images = process_bounds and importlib.util.find_spec("PIL") is not None
    return {
        "max_attachment_bytes": MAX_ATTACHMENT_BYTES,
        "max_attachments_per_turn": MAX_REFS,
        "retention_seconds": RETENTION_SECONDS,
        "types": [
            *[
                {"media_type": mime, "available": True, "capability": "text_extraction"}
                for mime in sorted(_TEXT_MIMES)
            ],
            {"media_type": "application/pdf", "available": pdf, "capability": "pdf_text_extraction"},
            *[
                {
                    "media_type": mime,
                    "available": images,
                    "capability": "decoded_image_metadata",
                    "vision_available": False,
                    "ocr_available": False,
                }
                for mime in sorted(_IMAGE_MIMES)
            ],
            {
                "media_type": "audio/wav",
                "available": process_bounds,
                "capability": "decoded_pcm_metadata",
                "transcription_available": False,
            },
        ],
    }


def _bounded_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ChatAttachmentError("The file contains no extractable text")
    if "\x00" in text:
        raise ChatAttachmentError("The file contains binary data instead of plain text")
    if len(text.encode("utf-8")) > MAX_EXTRACTED_BYTES:
        raise ChatAttachmentError("Extracted text exceeds 48 KB; attach a smaller excerpt", 413)
    return text


def _extract_file(payload: bytes, media_type: str) -> dict:
    if media_type in _TEXT_MIMES:
        try:
            text = payload.decode("utf-8-sig", errors="strict")
        except UnicodeError as exc:
            raise ChatAttachmentError("Text files must contain valid UTF-8") from exc
        return {
            "text": _bounded_text(text),
            "capabilities": ["text_extraction"],
            "metadata": {"encoding": "UTF-8"},
        }
    if media_type == "application/pdf":
        try:
            from pypdf import PdfReader, __version__ as pdf_version
        except ImportError as exc:
            raise ChatAttachmentError("PDF text extraction is unavailable on this server", 503) from exc
        if not payload.startswith(b"%PDF-"):
            raise ChatAttachmentError("The file is not a PDF document")
        try:
            reader = PdfReader(io.BytesIO(payload), strict=True)
            if reader.is_encrypted:
                raise ChatAttachmentError("Encrypted PDFs cannot be attached")
            if not 1 <= len(reader.pages) <= 64:
                raise ChatAttachmentError("PDFs must contain between 1 and 64 pages", 413)
            extracted = []
            size = 0
            for index, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                size += len(page_text.encode())
                if size > MAX_EXTRACTED_BYTES:
                    raise ChatAttachmentError(
                        "Extracted PDF text exceeds 48 KB; attach a smaller excerpt", 413
                    )
                if page_text.strip():
                    extracted.append(f"[Page {index + 1}]\n{page_text}")
            if not extracted:
                raise ChatAttachmentError(
                    "This PDF has no extractable text. OCR is not available; attach its text instead"
                )
            return {
                "text": _bounded_text("\n\n".join(extracted)),
                "capabilities": ["pdf_text_extraction"],
                "metadata": {
                    "page_count": len(reader.pages),
                    "extractor": "pypdf@" + pdf_version,
                    "ocr_available": False,
                },
            }
        except ChatAttachmentError:
            raise
        except Exception as exc:
            raise ChatAttachmentError("PDF text extraction failed; the document may be malformed") from exc
    from skeleton.ai.runtime.multimodal.media_validation import MediaValidationLimits, validate_media

    modality = "image" if media_type in _IMAGE_MIMES else "audio"
    receipt = validate_media(
        payload,
        modality=modality,
        mime_type=media_type,
        limits=MediaValidationLimits(
            max_image_bytes=MAX_ATTACHMENT_BYTES,
            max_audio_bytes=MAX_ATTACHMENT_BYTES,
            max_pixels=1_000_000,
            max_dimension=4096,
            max_decoded_bytes=8 * 1024 * 1024,
            max_audio_seconds=60,
            max_audio_channels=2,
            max_metadata_bytes=16 * 1024,
        ),
    )
    metadata = receipt.as_dict()
    metadata["validation_digest"] = receipt.digest
    metadata["ocr_available"] = False
    metadata["transcription_available"] = False
    return {
        "text": "",
        "capabilities": ["decoded_image_metadata" if modality == "image" else "decoded_pcm_metadata"],
        "metadata": metadata,
    }


def _extract_worker(channel, payload: bytes, media_type: str) -> None:
    try:
        # File parsing is isolated from the HTTP process and has no provider,
        # network, database or tool credentials passed into it.
        retained_environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "PYTHONPATH", "LD_LIBRARY_PATH", "SYSTEMROOT", "TEMP", "TMPDIR"}
        }
        os.environ.clear()
        os.environ.update(retained_environment)

        def local_decoder_authority(event, _arguments):
            if event in {"socket.connect", "socket.bind", "subprocess.Popen", "os.system", "os.posix_spawn"}:
                raise PermissionError("file decoding has no network or external process authority")

        sys.addaudithook(local_decoder_authority)
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        except (ImportError, OSError, ValueError) as exc:
            if media_type not in _TEXT_MIMES:
                raise ChatAttachmentError(
                    "Bounded media/document parsing is unavailable on this server", 503
                ) from exc
        result = _extract_file(payload, media_type)
        channel.send({"ok": True, "result": result})
    except ChatAttachmentError as exc:
        channel.send({"ok": False, "detail": str(exc), "status_code": exc.status_code})
    except Exception:
        channel.send(
            {
                "ok": False,
                "detail": "The file cannot be decoded within the supported limits",
                "status_code": 422,
            }
        )
    finally:
        channel.close()


def _isolated_extract(payload: bytes, media_type: str) -> dict:
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_extract_worker, args=(writer, payload, media_type), daemon=True)
    try:
        process.start()
        writer.close()
        if not reader.poll(12):
            raise ChatAttachmentError("File decoding exceeded its time or memory limit", 422)
        try:
            response = reader.recv()
        except EOFError as exc:
            raise ChatAttachmentError("File decoding exceeded its time or memory limit", 422) from exc
        process.join(timeout=1)
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise ChatAttachmentError(
                response.get("detail", "File decoding failed"), response.get("status_code", 422)
            )
        return response["result"]
    finally:
        if process.pid is not None and process.is_alive():
            process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
        reader.close()
        writer.close()
        if process.pid is not None and not process.is_alive():
            process.close()


def _collection():
    from core.databases import core_db

    return core_db["chat_attachments"]


async def ensure_attachment_indexes() -> None:
    global _INDEX_READY
    if _INDEX_READY:
        return
    async with _INDEX_LOCK:
        if _INDEX_READY:
            return
        collection = _collection()
        await collection.create_index(
            [("tenant_id", 1), ("owner_id", 1), ("thread_id", 1), ("kind", 1), ("status", 1)],
            name="chat_attachment_owner_thread",
        )
        # Quota rows have no top-level expires_at. Their bounded allocations
        # retain enough identity to reclaim accounting even after Mongo's TTL.
        await collection.create_index("expires_at", expireAfterSeconds=0, name="chat_attachment_expiry")
        _INDEX_READY = True


async def _authorize(
    thread_id: str, tenant_id: str, owner_id: str, permission: str = "read", *, active: bool = True
):
    from core.conversations import conversation_authority
    from core.tenant_storage_boundary import (
        StorageDataClass,
        StorageSurface,
        TenantStorageContext,
        require_tenant_storage,
    )

    thread = await conversation_authority.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
    if not thread.writable and (active or thread.state.value != "archived"):
        raise ChatAttachmentError("Attachments require an active conversation", 409)
    require_tenant_storage(
        context=TenantStorageContext(
            tenant_id=tenant_id,
            principal_id=owner_id,
            granted_permissions=(permission,),
            data_class=StorageDataClass.ATTACHMENT_BYTES,
            surface=StorageSurface.CANONICAL_SERVER,
            purpose="chat-attachments",
        ),
        verified_tenant_id=tenant_id,
        requested_permission=permission,
    )
    return thread


def _scope(thread_id: str, tenant_id: str, owner_id: str) -> dict:
    return {"kind": "attachment", "thread_id": thread_id, "tenant_id": tenant_id, "owner_id": owner_id}


def _quota_id(tenant_id: str, owner_id: str) -> str:
    return "quota:" + _digest([tenant_id, owner_id])


def _thread_key(thread_id: str) -> str:
    return hashlib.sha256(thread_id.encode()).hexdigest()


async def _release_quota(attachment_id: str, tenant_id: str, owner_id: str) -> None:
    collection = _collection()
    quota_id = _quota_id(tenant_id, owner_id)
    document = await collection.find_one(
        {"_id": quota_id, "kind": "quota", "tenant_id": tenant_id, "owner_id": owner_id}
    )
    entry = (document or {}).get("allocations", {}).get(attachment_id)
    if entry is None:
        return
    key = _thread_key(entry["thread_id"])
    await collection.update_one(
        {"_id": quota_id, f"allocations.{attachment_id}": entry},
        {
            "$unset": {f"allocations.{attachment_id}": ""},
            "$inc": {"bytes": -entry["size_bytes"], "count": -1, f"threads.{key}": -1},
        },
    )
    await collection.update_one({"_id": quota_id, f"threads.{key}": 0}, {"$unset": {f"threads.{key}": ""}})


async def _cleanup_owner(tenant_id: str, owner_id: str) -> None:
    collection = _collection()
    document = await collection.find_one({"_id": _quota_id(tenant_id, owner_id), "kind": "quota"})
    allocations = (document or {}).get("allocations", {})
    if not isinstance(allocations, dict) or len(allocations) > MAX_OWNER_FILES:
        raise ChatAttachmentError("Attachment quota metadata is corrupt", 503)
    now = _now()
    existing = await collection.find(
        {
            "_id": {"$in": list(allocations)},
            "kind": "attachment",
            "tenant_id": tenant_id,
            "owner_id": owner_id,
        },
        {"_id": 1},
    ).to_list(length=MAX_OWNER_FILES)
    existing_ids = {row["_id"] for row in existing}
    for attachment_id, entry in allocations.items():
        orphan = (
            attachment_id not in existing_ids and _utc(entry["reserved_at"]) + timedelta(seconds=60) <= now
        )
        if orphan or _utc(entry["expires_at"]) <= now:
            await collection.update_one(
                {"_id": attachment_id, "kind": "attachment", "tenant_id": tenant_id, "owner_id": owner_id},
                {
                    "$set": {"status": "expired", "deleted_at": now},
                    "$unset": {"payload": "", "extracted_text": "", "context_text": "", "preview": ""},
                },
            )
            await _release_quota(attachment_id, tenant_id, owner_id)


async def _reserve_quota(
    attachment_id: str, thread_id: str, tenant_id: str, owner_id: str, size_bytes: int, expires_at: datetime
) -> None:
    collection = _collection()
    quota_id, key = _quota_id(tenant_id, owner_id), _thread_key(thread_id)
    await collection.update_one(
        {"_id": quota_id},
        {
            "$setOnInsert": {
                "kind": "quota",
                "tenant_id": tenant_id,
                "owner_id": owner_id,
                "bytes": 0,
                "count": 0,
                "threads": {},
                "allocations": {},
            }
        },
        upsert=True,
    )
    reserved = await collection.find_one_and_update(
        {
            "_id": quota_id,
            "kind": "quota",
            "tenant_id": tenant_id,
            "owner_id": owner_id,
            "bytes": {"$lte": MAX_OWNER_BYTES - size_bytes},
            "count": {"$lt": MAX_OWNER_FILES},
            "$or": [{f"threads.{key}": {"$exists": False}}, {f"threads.{key}": {"$lt": MAX_THREAD_FILES}}],
            f"allocations.{attachment_id}": {"$exists": False},
        },
        {
            "$set": {
                f"allocations.{attachment_id}": {
                    "thread_id": thread_id,
                    "size_bytes": size_bytes,
                    "expires_at": expires_at,
                    "reserved_at": _now(),
                }
            },
            "$inc": {"bytes": size_bytes, "count": 1, f"threads.{key}": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if reserved is None:
        raise ChatAttachmentError("Attachment storage is full; remove an attachment before uploading", 413)


def _identity(row: Mapping) -> dict:
    return {
        name: row[name]
        for name in (
            "attachment_id",
            "tenant_id",
            "owner_id",
            "thread_id",
            "filename",
            "media_type",
            "data_class",
            "size_bytes",
            "content_digest",
            "extracted_text_digest",
            "context_text_digest",
            "extractor_version",
            "capabilities",
            "metadata",
            "rights",
            "created_at_iso",
            "expires_at_iso",
        )
    }


def _public(row: Mapping) -> dict:
    return {
        "attachment_id": row["attachment_id"],
        "attachment_ref": ATTACHMENT_PREFIX + row["attachment_id"],
        "thread_id": row["thread_id"],
        "filename": row["filename"],
        "media_type": row["media_type"],
        "data_class": row["data_class"],
        "size_bytes": row["size_bytes"],
        "content_digest": row["content_digest"],
        "identity_digest": row["identity_digest"],
        "expires_at": row["expires_at_iso"],
        "capabilities": row["capabilities"],
        "metadata": row["metadata"],
        "preview": row.get("preview", ""),
        "status": row["status"],
        "instruction_trusted": False,
    }


def _validate_row(row: Mapping, *, pending: bool = False) -> None:
    if row.get("status") != ("pending" if pending else "active") or _utc(row["expires_at"]) <= _now():
        raise ChatAttachmentError("This attachment was removed or expired; attach the file again", 410)
    payload = row.get("payload")
    if (
        not isinstance(payload, bytes)
        or not 1 <= len(payload) <= MAX_ATTACHMENT_BYTES
        or len(payload) != row["size_bytes"]
        or hashlib.sha256(payload).hexdigest() != row["content_digest"]
        or _digest(_identity(row)) != row["identity_digest"]
        or hashlib.sha256(row["extracted_text"].encode()).hexdigest() != row["extracted_text_digest"]
        or hashlib.sha256(row["context_text"].encode()).hexdigest() != row["context_text_digest"]
        or row["rights"] != ["conversation-inference"]
        or row["data_class"] not in {"confidential", "restricted"}
        or row.get("_id") != row["attachment_id"]
        or _utc(row["created_at"]).isoformat() != row["created_at_iso"]
        or _utc(row["expires_at"]).isoformat() != row["expires_at_iso"]
    ):
        raise ChatAttachmentError("Attachment identity or source content changed", 503)
    if not pending:
        admission, governance = row.get("storage_receipt"), row.get("governance_receipt")
        record = governance.get("record") if isinstance(governance, Mapping) else None
        if (
            not isinstance(admission, Mapping)
            or admission.get("tenant_id") != row["tenant_id"]
            or admission.get("resource_id") != row["attachment_id"]
            or admission.get("capability") != "conversation-persistence"
            or admission.get("write_id") != "chat-attachment:" + row["attachment_id"]
            or not isinstance(record, Mapping)
            or record.get("tenant_id") != row["tenant_id"]
            or record.get("record_id") != row["attachment_id"]
            or record.get("source_ref")
            != f"conversation-attachment://{row['thread_id']}/{row['attachment_id']}"
            or record.get("owner_plane") != "conversation"
            or record.get("state") != "active"
            or record.get("data_class") != row["data_class"]
            or record.get("purposes") != ["model-inference"]
            or record.get("deletion_targets") != ["conversation"]
        ):
            raise ChatAttachmentError("Attachment admission or governance proof changed", 503)


async def upload_attachment(
    *,
    thread_id: str,
    tenant_id: str,
    owner_id: str,
    filename: str,
    media_type: str,
    encoded: str,
    rights_acknowledged: bool,
    upload_id: str | None = None,
) -> dict:
    if rights_acknowledged is not True:
        raise ChatAttachmentError("Confirm permission to use the file in this conversation", 403)
    thread_id, tenant_id, owner_id = (
        _text(value, label)
        for value, label in ((thread_id, "Conversation"), (tenant_id, "Tenant"), (owner_id, "Owner"))
    )
    name = safe_filename(filename)
    mime = _text(media_type, "Media type", 128).lower()
    if mime not in _ALL_MIMES:
        raise ChatAttachmentError("This file type is not supported", 415)
    if not isinstance(encoded, str) or not encoded or len(encoded) > MAX_BASE64_CHARS:
        raise ChatAttachmentError("Attachments must be smaller than 5 MB", 413)
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ChatAttachmentError("Attachment encoding is invalid") from exc
    if not 1 <= len(payload) <= MAX_ATTACHMENT_BYTES:
        raise ChatAttachmentError("Attachments must be nonempty and smaller than 5 MB", 413)
    upload_key = _attachment_id(upload_id or str(uuid4()))
    attachment_id = str(
        uuid5(NAMESPACE_URL, _json(["chat-attachment", tenant_id, owner_id, thread_id, upload_key]))
    )
    request_digest = _digest(
        [thread_id, name, mime, hashlib.sha256(payload).hexdigest(), rights_acknowledged]
    )
    thread = await _authorize(thread_id, tenant_id, owner_id, "write")
    data_class = "restricted" if thread.data_class == "restricted" else "confidential"
    await ensure_attachment_indexes()
    collection = _collection()
    existing = await collection.find_one({"_id": attachment_id, **_scope(thread_id, tenant_id, owner_id)})
    if existing is not None:
        if existing.get("request_digest") != request_digest:
            raise ChatAttachmentError("This upload identity belongs to a different file", 409)
        if existing.get("status") == "pending":
            _validate_row(existing, pending=True)
            if _utc(existing["lease_until"]) > _now():
                raise ChatAttachmentError("This file upload is still being committed; retry shortly", 409)
            worker = str(uuid4())
            recovered = await collection.find_one_and_update(
                {
                    "_id": attachment_id,
                    **_scope(thread_id, tenant_id, owner_id),
                    "status": "pending",
                    "$expr": {"$lte": ["$lease_until", "$$NOW"]},
                },
                {"$set": {"lease_owner": worker, "lease_until": _now() + timedelta(seconds=60)}},
                return_document=ReturnDocument.AFTER,
            )
            if recovered is None:
                raise ChatAttachmentError("Another worker is recovering this upload; retry shortly", 409)
            return await _commit_attachment(recovered, worker)
        _validate_row(existing)
        return _public(existing)
    await _cleanup_owner(tenant_id, owner_id)
    try:
        await asyncio.wait_for(_UPLOAD_SLOTS.acquire(), timeout=1)
    except TimeoutError as exc:
        raise ChatAttachmentError("The file extractor is busy; retry shortly", 429) from exc
    try:
        work = asyncio.create_task(asyncio.to_thread(_isolated_extract, payload, mime))
        try:
            extracted = await asyncio.shield(work)
        except asyncio.CancelledError:
            # Keep the slot until the bounded child has actually quiesced.
            try:
                await asyncio.shield(work)
            except Exception:
                pass
            raise
    finally:
        if work.done():
            _UPLOAD_SLOTS.release()
        else:
            work.add_done_callback(lambda _completed: _UPLOAD_SLOTS.release())
    created = _now()
    expires = created + timedelta(seconds=RETENTION_SECONDS)
    context_text = f"Uploaded file: {name}\nMedia type: {mime}\n" + (
        "Extracted file text (untrusted evidence):\n" + extracted["text"]
        if extracted["text"]
        else "Only the following decoded media metadata is available. Image content interpretation, OCR and audio transcription are unavailable.\n"
        + _json(extracted["metadata"])
    )
    row = {
        "_id": attachment_id,
        "attachment_id": attachment_id,
        **_scope(thread_id, tenant_id, owner_id),
        "filename": name,
        "media_type": mime,
        "data_class": data_class,
        "size_bytes": len(payload),
        "payload": payload,
        "extracted_text": extracted["text"],
        "context_text": context_text,
        "preview": extracted["text"][:500],
        "content_digest": hashlib.sha256(payload).hexdigest(),
        "extracted_text_digest": hashlib.sha256(extracted["text"].encode()).hexdigest(),
        "context_text_digest": hashlib.sha256(context_text.encode()).hexdigest(),
        "extractor_version": EXTRACTOR_VERSION,
        "capabilities": extracted["capabilities"],
        "metadata": extracted["metadata"],
        "rights": ["conversation-inference"],
        "created_at": created,
        "expires_at": expires,
        "created_at_iso": created.isoformat(),
        "expires_at_iso": expires.isoformat(),
        "status": "pending",
        "request_digest": request_digest,
        "lease_owner": str(uuid4()),
        "lease_until": created + timedelta(seconds=60),
    }
    row["identity_digest"] = _digest(_identity(row))
    await _reserve_quota(attachment_id, thread_id, tenant_id, owner_id, len(payload), expires)
    try:
        await collection.insert_one(row)
    except BaseException:
        # A lost Mongo acknowledgement does not prove the insert failed. Keep
        # its reservation if durable pending state exists so recovery cannot
        # publish bytes outside the atomically admitted owner allocation.
        durable = await collection.find_one(
            {"_id": attachment_id, **_scope(thread_id, tenant_id, owner_id)}, {"_id": 1}
        )
        if durable is None:
            await _release_quota(attachment_id, tenant_id, owner_id)
        raise
    return await _commit_attachment(row, row["lease_owner"])


async def _commit_attachment(row: dict, worker: str) -> dict:
    """Recover pending admission using original immutable bytes and receipt IDs."""
    from core.conversations import conversation_authority

    attachment_id, tenant_id, owner_id, thread_id = (
        row["attachment_id"],
        row["tenant_id"],
        row["owner_id"],
        row["thread_id"],
    )
    collection = _collection()
    registered = False
    try:
        _validate_row(row, pending=True)
        quota = await collection.find_one(
            {
                "_id": _quota_id(tenant_id, owner_id),
                "kind": "quota",
                "tenant_id": tenant_id,
                "owner_id": owner_id,
            }
        )
        allocation = (quota or {}).get("allocations", {}).get(attachment_id)
        if (
            not isinstance(allocation, dict)
            or allocation.get("thread_id") != thread_id
            or allocation.get("size_bytes") != row["size_bytes"]
            or _utc(allocation["expires_at"]) != _utc(row["expires_at"])
        ):
            raise ChatAttachmentError("Attachment storage allocation is unavailable", 503)
        admitter, registrar = (
            conversation_authority.storage_admitter,
            conversation_authority.governance_registrar,
        )
        if admitter is None or registrar is None:
            raise ChatAttachmentError("Governed attachment storage is unavailable", 503)
        storage_bytes = (
            row["size_bytes"]
            + len(row["context_text"].encode())
            + len(row["extracted_text"].encode())
            + 65536
        )
        admission = await admitter(
            tenant_id=tenant_id,
            capability="conversation-persistence",
            resource_id=attachment_id,
            write_id="chat-attachment:" + attachment_id,
            storage_bytes=storage_bytes,
        )
        if (
            not isinstance(admission, Mapping)
            or type(admission.get("storage_bytes")) is not int
            or admission["storage_bytes"] != storage_bytes
            or admission.get("tenant_id") != tenant_id
            or admission.get("capability") != "conversation-persistence"
            or admission.get("resource_id") != attachment_id
            or admission.get("write_id") != "chat-attachment:" + attachment_id
        ):
            raise ChatAttachmentError("Attachment storage admission is invalid", 503)
        await _authorize(thread_id, tenant_id, owner_id, "write")
        registered = True
        governance = await registrar(
            mode="register",
            plane="conversation",
            record_id=attachment_id,
            tenant_id=tenant_id,
            source_ref=f"conversation-attachment://{thread_id}/{attachment_id}",
            data_class=row["data_class"],
            purposes=("model-inference",),
            deletion_targets=("conversation",),
            created_at=_utc(row["created_at"]).timestamp(),
            retention_until=_utc(row["expires_at"]).timestamp(),
            exportable=True,
        )
        record = governance.get("record", {}) if isinstance(governance, Mapping) else {}
        if (
            record.get("record_id") != attachment_id
            or record.get("tenant_id") != tenant_id
            or record.get("owner_plane") != "conversation"
            or record.get("state") != "active"
            or record.get("source_ref") != f"conversation-attachment://{thread_id}/{attachment_id}"
            or record.get("data_class") != row["data_class"]
            or record.get("purposes") != ["model-inference"]
            or record.get("deletion_targets") != ["conversation"]
        ):
            raise ChatAttachmentError("Attachment governance identity is invalid", 503)
        if len(_json([admission, governance]).encode()) > 32768:
            raise ChatAttachmentError("Attachment storage receipts exceed their bounds", 503)
        await _authorize(thread_id, tenant_id, owner_id, "write")
        result = await collection.update_one(
            {
                "_id": attachment_id,
                **_scope(thread_id, tenant_id, owner_id),
                "status": "pending",
                "lease_owner": worker,
                "$expr": {"$gt": ["$lease_until", "$$NOW"]},
            },
            {
                "$set": {
                    "status": "active",
                    "storage_receipt": dict(admission),
                    "governance_receipt": dict(governance),
                },
                "$unset": {"lease_owner": "", "lease_until": ""},
            },
        )
        if result.modified_count != 1:
            raise ChatAttachmentError(
                "The upload worker expired or the attachment was retired before publication", 409
            )
        row["status"] = "active"
        return _public(row)
    except BaseException:
        retired = await collection.update_one(
            {
                "_id": attachment_id,
                **_scope(thread_id, tenant_id, owner_id),
                "status": "pending",
                "lease_owner": worker,
            },
            {
                "$set": {"status": "deleted", "deleted_at": _now()},
                "$unset": {
                    "payload": "",
                    "extracted_text": "",
                    "context_text": "",
                    "preview": "",
                    "lease_owner": "",
                    "lease_until": "",
                },
            },
        )
        if retired.matched_count:
            await _release_quota(attachment_id, tenant_id, owner_id)
        if registered:
            current = await collection.find_one(
                {"_id": attachment_id, **_scope(thread_id, tenant_id, owner_id)}, {"status": 1}
            )
            if current is None or current.get("status") in {"deleted", "expired"}:
                try:
                    await conversation_authority.execute_governed_deletion(
                        tenant_id=tenant_id, record_ids=(attachment_id,), reason="attachment-upload-aborted"
                    )
                except Exception:
                    # Original bytes are already gone. The canonical lifecycle
                    # owner retries any remaining acknowledgement/retention.
                    pass
        raise


async def get_attachment(reference: str, *, thread_id: str, tenant_id: str, owner_id: str) -> dict:
    await _authorize(thread_id, tenant_id, owner_id, active=False)
    row = await _collection().find_one(
        {"_id": _attachment_id(reference), **_scope(thread_id, tenant_id, owner_id)}
    )
    if row is None:
        raise ChatAttachmentError("Attachment not found", 404)
    _validate_row(row)
    return _public(row)


async def delete_attachment(reference: str, *, thread_id: str, tenant_id: str, owner_id: str) -> dict:
    await _authorize(thread_id, tenant_id, owner_id, "delete", active=False)
    identifier = _attachment_id(reference)
    result = await _collection().update_one(
        {"_id": identifier, **_scope(thread_id, tenant_id, owner_id)},
        {
            "$set": {"status": "deleted", "deleted_at": _now()},
            "$unset": {"payload": "", "extracted_text": "", "context_text": "", "preview": ""},
        },
    )
    if not result.matched_count:
        raise ChatAttachmentError("Attachment not found", 404)
    await _release_quota(identifier, tenant_id, owner_id)
    from core.conversations import conversation_authority

    await conversation_authority.execute_governed_deletion(
        tenant_id=tenant_id, record_ids=(identifier,), reason="attachment-owner-delete"
    )
    return {"attachment_ref": ATTACHMENT_PREFIX + identifier, "deleted": True}


async def retire_attachment_record(attachment_id: str, *, tenant_id: str) -> bool:
    """Physical scrub for an already authorized canonical lifecycle action."""
    identifier = _attachment_id(attachment_id)
    collection = _collection()
    row = await collection.find_one(
        {"_id": identifier, "kind": "attachment", "tenant_id": tenant_id},
        {"owner_id": 1, "attachment_id": 1},
    )
    if row is None:
        return False
    await collection.update_one(
        {"_id": identifier, "kind": "attachment", "tenant_id": tenant_id},
        {
            "$set": {"status": "deleted", "deleted_at": _now()},
            "$unset": {"payload": "", "extracted_text": "", "context_text": "", "preview": ""},
        },
    )
    await _release_quota(identifier, tenant_id, row["owner_id"])
    return True


async def retire_conversation_attachments(thread_id: str, *, tenant_id: str, owner_id: str) -> int:
    """Called after the conversation owner's deleting/version fence."""
    collection = _collection()
    rows = await collection.find(
        {**_scope(thread_id, tenant_id, owner_id), "status": {"$in": ["active", "pending"]}},
        {"attachment_id": 1},
    ).to_list(length=MAX_OWNER_FILES + 1)
    if len(rows) > MAX_OWNER_FILES:
        raise ChatAttachmentError("Conversation attachment inventory exceeds its bound", 503)
    await collection.update_many(
        _scope(thread_id, tenant_id, owner_id),
        {
            "$set": {"status": "deleted", "deleted_at": _now()},
            "$unset": {"payload": "", "extracted_text": "", "context_text": "", "preview": ""},
        },
    )
    for row in rows:
        await _release_quota(row["attachment_id"], tenant_id, owner_id)
    return len(rows)


@dataclass(frozen=True, slots=True)
class AttachmentContextResolution:
    segments: tuple[ContextSegment, ...]
    identity_refs: tuple[str, ...]
    attachments: tuple[dict, ...]


async def resolve_attachment_context(
    *, thread_id: str, tenant_id: str, owner_id: str, attachment_refs: Sequence[str], created_at: datetime
) -> AttachmentContextResolution:
    if (
        isinstance(attachment_refs, (str, bytes))
        or not isinstance(attachment_refs, Sequence)
        or len(attachment_refs) > MAX_REFS
    ):
        raise ChatAttachmentError("At most four attachment references can be admitted", 413)
    if len(set(attachment_refs)) != len(attachment_refs):
        raise ChatAttachmentError("Attachment references must be unique")
    if not attachment_refs:
        return AttachmentContextResolution((), (), ())
    await _authorize(thread_id, tenant_id, owner_id)
    segments, identities, attachments = [], [], []
    total = 0
    for reference in attachment_refs:
        if not isinstance(reference, str) or not reference.startswith(ATTACHMENT_PREFIX):
            raise ChatAttachmentError("Attachment references must be issued by this conversation")
        identifier = _attachment_id(reference)
        row = await _collection().find_one({"_id": identifier, **_scope(thread_id, tenant_id, owner_id)})
        if row is None:
            raise ChatAttachmentError("Attachment not found", 404)
        _validate_row(row)
        total += len(row["context_text"].encode())
        if total > MAX_CONTEXT_BYTES:
            raise ChatAttachmentError("Attachment context exceeds 128 KB; send fewer files", 413)
        refs = (
            reference,
            f"conversation-attachment://{thread_id}/{identifier}",
            "attachment-source-sha256:" + row["content_digest"],
            "attachment-identity-sha256:" + row["identity_digest"],
            "attachment-text-sha256:" + row["extracted_text_digest"],
            "attachment-rights:conversation-inference",
        )
        identities.extend(refs)
        segments.append(
            artifact_segment(
                artifact_id=identifier,
                content=row["context_text"],
                tenant_id=tenant_id,
                purpose="model-inference",
                created_at=_utc(created_at),
                data_class=row["data_class"],
                content_ref=reference,
                provenance=refs,
                retention_class="conversation-attachment-24h",
            )
        )
        attachments.append(_public(row))
    await _authorize(thread_id, tenant_id, owner_id)
    # Recheck publication after materialization; deletion/expiry cannot revive
    # bytes simply because an earlier projection was cached in the request.
    for attachment in attachments:
        live = await _collection().find_one(
            {"_id": attachment["attachment_id"], **_scope(thread_id, tenant_id, owner_id)},
            {"status": 1, "expires_at": 1, "identity_digest": 1},
        )
        if (
            live is None
            or live.get("status") != "active"
            or _utc(live["expires_at"]) <= _now()
            or live.get("identity_digest") != attachment["identity_digest"]
        ):
            raise ChatAttachmentError("Attachment was removed or expired before context admission", 410)
    return AttachmentContextResolution(tuple(segments), tuple(dict.fromkeys(identities)), tuple(attachments))
