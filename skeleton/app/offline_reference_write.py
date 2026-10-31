"""Operator-approved write into the local reference library.

The model does not choose this tool. An authenticated operator request must
set ``approved`` to true and then present the approval reference bound to that
exact title and text. The canonical tool runtime withholds the write until
that reference matches. Rollback deletes only the document that receipt
created.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any
from uuid import UUID

from skeleton.app.offline_knowledge import (
    MAX_TITLE_BYTES,
    OfflineKnowledgeLibrary,
    _terms,
)
from skeleton.skills.tool_contract import (
    ToolApprovalPolicy,
    ToolAuthorityClass,
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolIdempotencyMode,
    ToolManifest,
    ToolRiskClass,
    ToolSideEffectClass,
    approval_ref_for_request,
)
from skeleton.skills.tool_runtime import ToolExecutionConflict, ToolRuntime


TOOL_ID = "local.reference.write"
_UNSAFE = re.compile(
    r"(?:\.\./|\\|\||;|`|\$\(|://|(?:^|/)\.\.(?:/|$)|ignore previous|"
    r"system prompt|file:)",
    re.IGNORECASE,
)


class ReferenceWriteDenied(PermissionError):
    """The operator did not approve this write."""


class ReferenceWriteRejected(ValueError):
    """The write request is outside the local library contract."""


class ReferenceWriteConflict(ReferenceWriteRejected):
    """The same request id was reused for a different document."""


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ReferenceWriteRejected("request id must be a canonical UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ReferenceWriteRejected("request id must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ReferenceWriteRejected("request id must be a canonical UUID")
    return value


def _title(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReferenceWriteRejected("title must contain text")
    if value != value.strip() or "\x00" in value:
        raise ReferenceWriteRejected("title must be normalized")
    if len(value.encode("utf-8")) > MAX_TITLE_BYTES:
        raise ReferenceWriteRejected("title exceeds the local reference budget")
    if value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value):
        raise ReferenceWriteRejected("filesystem paths are outside the reference library")
    if _UNSAFE.search(value):
        raise ReferenceWriteRejected("title is outside the local reference write contract")
    return value


def _body(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReferenceWriteRejected("text must contain text")
    if value != value.strip() or "\x00" in value:
        raise ReferenceWriteRejected("text must be normalized")
    if not _terms(value):
        raise ReferenceWriteRejected("text has no searchable terms")
    return value


def _approval(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ReferenceWriteRejected("approval ref must be a normalized string")
    if len(value) > 1024 or not value.startswith("approval:"):
        raise ReferenceWriteRejected("approval ref is outside the write contract")
    return value


def _manifest() -> ToolManifest:
    return ToolManifest(
        tool_id=TOOL_ID,
        version="1",
        description="Add one operator-approved document to the local reference library.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "text"],
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": MAX_TITLE_BYTES},
                "text": {"type": "string", "minLength": 1},
            },
        },
        effect=ToolEffect.REVERSIBLE,
        authority_class=ToolAuthorityClass.WRITE,
        risk_class=ToolRiskClass.MEDIUM,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.IDEMPOTENCY_KEY,
        approval_policy=ToolApprovalPolicy.ALWAYS,
        approval_required=True,
        network_policy="none",
        data_policy="internal",
        timeout_seconds=5.0,
        result_size_limit=4_096,
    )


class LocalReferenceWrite:
    """One reversible write tool bound to one local library."""

    def __init__(self, library: OfflineKnowledgeLibrary) -> None:
        if not isinstance(library, OfflineKnowledgeLibrary):
            raise TypeError("library must be an OfflineKnowledgeLibrary")
        self.library = library
        self.runtime = ToolRuntime()
        self._payloads: dict[str, dict[str, Any]] = {}
        self._rolled_back: set[str] = set()
        self.runtime.register(_manifest(), self._execute)

    def _execute(self, request: ToolExecutionRequest) -> str:
        title = _title(request.arguments.get("title"))
        text = _body(request.arguments.get("text"))
        record = self.library.add_text(title, text)
        payload = {
            "document_id": record["document_id"],
            "title": record["title"],
            "sha256": record["sha256"],
            "created": record["reused"] is False,
            "request_id": request.request_id,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        ref = TOOL_ID + ":" + sha256(encoded).hexdigest()[:24]
        self._payloads[ref] = payload
        return ref

    def _request(
        self,
        title: str,
        text: str,
        identity: str,
        approval_ref: str | None,
        instant: datetime,
    ) -> ToolExecutionRequest:
        return ToolExecutionRequest(
            request_id=identity,
            operation_id=identity,
            tenant_id="offline-local",
            tool_id=TOOL_ID,
            idempotency_key=identity,
            arguments={"title": title, "text": text},
            requested_at=instant,
            approval_ref=approval_ref,
        )

    def _view(self, receipt, identity: str, expected: str, existing) -> dict[str, Any]:
        payload = self._payloads.get(receipt.result_ref or "")
        return {
            "tool_id": TOOL_ID,
            "status": receipt.status.value,
            "receipt_id": receipt.receipt_id,
            "request_id": identity,
            "arguments_digest": receipt.arguments_digest,
            "result_ref": receipt.result_ref,
            "error_code": receipt.error_code,
            "approval_ref": receipt.approval_ref,
            "expected_approval_ref": expected,
            "replayed": existing is not None and receipt.status is ToolExecutionStatus.SUCCEEDED,
            "document_id": None if payload is None else payload["document_id"],
            "created": bool(payload and payload["created"]),
            "written": receipt.status is ToolExecutionStatus.SUCCEEDED,
            "authority": "operator_approval_reversible_write",
            "interpretation": "library_document_not_instruction",
        }

    def write(
        self,
        title: object,
        text: object,
        request_id: object,
        *,
        approved: object,
        approval_ref: object = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if type(approved) is not bool:
            raise ReferenceWriteRejected("approved must be a boolean")
        if approved is not True:
            raise ReferenceWriteDenied("reference writes require explicit operator approval")
        normalized_title = _title(title)
        normalized_text = _body(text)
        identity = _uuid(request_id)
        bound = _approval(approval_ref)
        instant = now if now is not None else datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ReferenceWriteRejected("request time must be timezone-aware")
        request = self._request(normalized_title, normalized_text, identity, bound, instant)
        expected = approval_ref_for_request(request)
        existing = self.runtime.receipt(
            tenant_id="offline-local",
            operation_id=identity,
            idempotency_key=identity,
        )
        try:
            receipt = self.runtime.execute(request, now=instant)
        except ToolExecutionConflict as exc:
            raise ReferenceWriteConflict("reference write request id reused") from exc
        return self._view(receipt, identity, expected, existing)

    def rollback(
        self,
        request_id: object,
        *,
        approved: object,
    ) -> dict[str, Any]:
        if type(approved) is not bool:
            raise ReferenceWriteRejected("approved must be a boolean")
        if approved is not True:
            raise ReferenceWriteDenied("reference rollback requires explicit operator approval")
        identity = _uuid(request_id)
        if identity in self._rolled_back:
            raise ReferenceWriteRejected("reference write already rolled back")
        receipt = self.runtime.receipt(
            tenant_id="offline-local",
            operation_id=identity,
            idempotency_key=identity,
        )
        if receipt is None or receipt.status is not ToolExecutionStatus.SUCCEEDED:
            raise ReferenceWriteRejected("no committed reference write to roll back")
        payload = self._payloads.get(receipt.result_ref or "")
        if payload is None or payload.get("created") is not True:
            raise ReferenceWriteRejected("this receipt did not create a document")
        document_id = payload["document_id"]
        self.library.delete(document_id)
        self._rolled_back.add(identity)
        return {
            "tool_id": TOOL_ID,
            "request_id": identity,
            "document_id": document_id,
            "rolled_back": True,
            "authority": "operator_approval_reversible_write",
        }
