"""Boundary adapters between runtime execution, durable events and memory.

The runtime, event bus and memory store remain separate canonical primitives.
This module only translates their existing contracts so execution outcomes can
cross durable boundaries without losing provenance or idempotency identity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from skeleton.frontier.agent_runtime import ExecutionResult
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent


_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"runtime outcome event {field_name} must be a non-empty string")
    return value


def _require_sha256(value: object, field_name: str) -> str:
    digest = _require_text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX_DIGITS for character in digest):
        raise ValueError(
            f"runtime outcome event {field_name} must be a lowercase SHA-256 digest"
        )
    return digest


def _require_aware_timestamp(value: object, field_name: str) -> str:
    text = _require_text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"runtime outcome event {field_name} must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"runtime outcome event {field_name} must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def execution_result_to_event(result: ExecutionResult) -> DomainEvent:
    """Convert one runtime result into a JSON-safe, provenance-bound event."""

    if result.provenance is None:
        raise ValueError("execution result requires provenance before publication")
    if result.started_at.tzinfo is None or result.finished_at.tzinfo is None:
        raise ValueError("execution timestamps must be timezone-aware")

    provenance = result.provenance.as_dict()
    task_sha256 = stable_content_digest(result.task)
    idempotency_sha256 = result.provenance.metadata.get("idempotency_key_sha256")
    identity_material = {
        "agent": result.agent,
        "task_sha256": task_sha256,
        "started_at": result.started_at.astimezone(timezone.utc).isoformat(),
        "finished_at": result.finished_at.astimezone(timezone.utc).isoformat(),
        "artifact_sha256": result.provenance.content_sha256,
        "idempotency_key_sha256": idempotency_sha256,
        "operation": result.provenance.operation,
    }
    execution_identity = stable_content_digest(identity_material)

    payload: dict[str, Any] = {
        "execution_identity_sha256": execution_identity,
        "agent": result.agent,
        "succeeded": result.succeeded,
        "task_sha256": task_sha256,
        "artifact_sha256": result.provenance.content_sha256,
        "started_at": identity_material["started_at"],
        "finished_at": identity_material["finished_at"],
        "provenance": provenance,
    }
    if idempotency_sha256 is not None:
        payload["idempotency_key_sha256"] = str(idempotency_sha256)
    if result.error is not None:
        payload["error"] = result.error

    return DomainEvent(
        topic="runtime.completed" if result.succeeded else "runtime.failed",
        payload=payload,
        occurred_at=result.finished_at.astimezone(timezone.utc),
    )


def execution_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    """Normalize a runtime outcome event into the existing memory contract.

    The consumer revalidates the producer-bound execution identity before using
    it as the memory id. This makes repeat at-least-once delivery idempotent and
    prevents a tampered event from reusing a valid execution id to overwrite a
    different runtime outcome.
    """

    if event.topic not in {"runtime.completed", "runtime.failed"}:
        raise ValueError("expected a runtime outcome event")

    provenance = event.payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise TypeError("runtime outcome event provenance must be a mapping")

    execution_id = _require_sha256(
        event.payload.get("execution_identity_sha256"),
        "execution_identity_sha256",
    )
    agent = _require_text(event.payload.get("agent"), "agent")
    artifact_sha256 = _require_sha256(
        event.payload.get("artifact_sha256"),
        "artifact_sha256",
    )
    task_sha256 = _require_sha256(
        event.payload.get("task_sha256"),
        "task_sha256",
    )
    started_at = _require_aware_timestamp(event.payload.get("started_at"), "started_at")
    finished_at = _require_aware_timestamp(
        event.payload.get("finished_at"),
        "finished_at",
    )
    operation = _require_text(provenance.get("operation"), "provenance.operation")

    provenance_artifact = _require_sha256(
        provenance.get("content_sha256"),
        "provenance.content_sha256",
    )
    if provenance_artifact != artifact_sha256:
        raise ValueError("runtime outcome event artifact digest disagrees with provenance")

    succeeded = event.payload.get("succeeded")
    if not isinstance(succeeded, bool):
        raise TypeError("runtime outcome event succeeded must be a boolean")
    expected_topic = "runtime.completed" if succeeded else "runtime.failed"
    if event.topic != expected_topic:
        raise ValueError("runtime outcome event topic disagrees with succeeded state")

    idempotency_sha256: str | None = None
    raw_idempotency = event.payload.get("idempotency_key_sha256")
    if raw_idempotency is not None:
        idempotency_sha256 = _require_sha256(
            raw_idempotency,
            "idempotency_key_sha256",
        )

    provenance_metadata = provenance.get("metadata")
    if provenance_metadata is not None and not isinstance(provenance_metadata, Mapping):
        raise TypeError("runtime outcome event provenance metadata must be a mapping")
    if isinstance(provenance_metadata, Mapping):
        provenance_idempotency = provenance_metadata.get("idempotency_key_sha256")
        if provenance_idempotency is not None:
            provenance_idempotency = _require_sha256(
                provenance_idempotency,
                "provenance.metadata.idempotency_key_sha256",
            )
            if provenance_idempotency != idempotency_sha256:
                raise ValueError(
                    "runtime outcome event idempotency digest disagrees with provenance"
                )

    identity_material = {
        "agent": agent,
        "task_sha256": task_sha256,
        "started_at": started_at,
        "finished_at": finished_at,
        "artifact_sha256": artifact_sha256,
        "idempotency_key_sha256": idempotency_sha256,
        "operation": operation,
    }
    expected_execution_id = stable_content_digest(identity_material)
    if execution_id != expected_execution_id:
        raise ValueError("runtime outcome event execution identity digest mismatch")

    metadata: dict[str, Any] = {
        "event_topic": event.topic,
        "agent": agent,
        "succeeded": succeeded,
        "task_sha256": task_sha256,
        "artifact_sha256": artifact_sha256,
        "execution_identity_sha256": execution_id,
        "source_repository": str(provenance.get("source_repository") or ""),
        "source_revision": provenance.get("source_revision"),
        "source_path": provenance.get("source_path"),
        "operation": operation,
    }
    if idempotency_sha256 is not None:
        metadata["idempotency_key_sha256"] = idempotency_sha256

    return {
        "id": execution_id,
        "content": f"{event.topic} {agent} {artifact_sha256}",
        "metadata": metadata,
    }
