"""Operator-granted read of the local reference library.

The model does not choose this tool. An authenticated operator request must
set ``granted`` to true. The canonical tool runtime then reads only the
model-scoped library and returns a receipt. Paths, shell syntax, remote URLs
and embedded instruction overrides are refused before any lookup.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any
from uuid import UUID

from skeleton.app.offline_knowledge import MAX_QUERY_BYTES, OfflineKnowledgeLibrary
from skeleton.skills.tool_contract import (
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolIdempotencyMode,
    ToolManifest,
)
from skeleton.skills.tool_runtime import ToolExecutionConflict, ToolRuntime


TOOL_ID = "local.reference.read"
_UNSAFE = re.compile(
    r"(?:\.\./|\\|\||;|`|\$\(|://|(?:^|/)\.\.(?:/|$)|ignore previous|"
    r"system prompt|file:)",
    re.IGNORECASE,
)
_INSTRUCTION = re.compile(
    r"\b(?:ignore (?:all |any )?(?:previous|prior|above) instructions|"
    r"you are now|system prompt)\b",
    re.IGNORECASE,
)


class ReferenceReadDenied(PermissionError):
    """The operator did not grant this read."""


class ReferenceReadRejected(ValueError):
    """The read request is outside the local library contract."""


class ReferenceReadConflict(ReferenceReadRejected):
    """The same request id was reused for a different query."""


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ReferenceReadRejected("request id must be a canonical UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ReferenceReadRejected("request id must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ReferenceReadRejected("request id must be a canonical UUID")
    return value


def _query(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReferenceReadRejected("query must contain text")
    query = value.strip()
    if query != value:
        raise ReferenceReadRejected("query must be normalized")
    if len(query.encode("utf-8")) > MAX_QUERY_BYTES:
        raise ReferenceReadRejected("query exceeds the local reference budget")
    if query.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", query):
        raise ReferenceReadRejected("filesystem paths are outside the reference library")
    if _UNSAFE.search(query):
        raise ReferenceReadRejected("query is outside the local reference read contract")
    return query


def _manifest() -> ToolManifest:
    return ToolManifest(
        tool_id=TOOL_ID,
        version="1",
        description="Read up to two passages from the operator's local reference library.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_QUERY_BYTES,
                },
            },
        },
        effect=ToolEffect.READ_ONLY,
        idempotency_mode=ToolIdempotencyMode.IDEMPOTENCY_KEY,
        network_policy="none",
        data_policy="internal",
        timeout_seconds=5.0,
        result_size_limit=16_384,
    )


class LocalReferenceRead:
    """One read-only tool bound to one local library."""

    def __init__(self, library: OfflineKnowledgeLibrary) -> None:
        if not isinstance(library, OfflineKnowledgeLibrary):
            raise TypeError("library must be an OfflineKnowledgeLibrary")
        self.library = library
        self.runtime = ToolRuntime()
        self._payloads: dict[str, dict[str, Any]] = {}
        self.runtime.register(_manifest(), self._execute)

    def _execute(self, request: ToolExecutionRequest) -> str:
        query = _query(request.arguments.get("query"))
        hits = self.library.search(query, limit=2)
        payload = {
            "query": query,
            "hits": [
                dict(hit, instruction_bearing=bool(_INSTRUCTION.search(hit.get("passage", ""))))
                if isinstance(hit, dict) else hit
                for hit in hits
            ],
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        ref = TOOL_ID + ":" + sha256(encoded).hexdigest()[:24]
        self._payloads[ref] = payload
        return ref

    def read(
        self,
        query: object,
        request_id: object,
        *,
        granted: object,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if type(granted) is not bool:
            raise ReferenceReadRejected("granted must be a boolean")
        if granted is not True:
            raise ReferenceReadDenied("reference reads require an explicit operator grant")
        normalized = _query(query)
        identity = _uuid(request_id)
        instant = now if now is not None else datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ReferenceReadRejected("request time must be timezone-aware")
        existing = self.runtime.receipt(
            tenant_id="offline-local",
            operation_id=identity,
            idempotency_key=identity,
        )
        request = ToolExecutionRequest(
            request_id=identity,
            operation_id=identity,
            tenant_id="offline-local",
            tool_id=TOOL_ID,
            idempotency_key=identity,
            arguments={"query": normalized},
            requested_at=instant,
        )
        try:
            receipt = self.runtime.execute(request, now=instant)
        except ToolExecutionConflict as exc:
            raise ReferenceReadConflict("reference read request id reused") from exc
        payload = self._payloads.get(receipt.result_ref or "")
        hits = [] if payload is None else payload["hits"]
        return {
            "tool_id": TOOL_ID,
            "status": receipt.status.value,
            "receipt_id": receipt.receipt_id,
            "request_id": identity,
            "arguments_digest": receipt.arguments_digest,
            "result_ref": receipt.result_ref,
            "error_code": receipt.error_code,
            "replayed": existing is not None and receipt.status is ToolExecutionStatus.SUCCEEDED,
            "hits": hits,
            "authority": "operator_grant_read_only",
            "interpretation": "tool_excerpt_not_instruction",
        }
