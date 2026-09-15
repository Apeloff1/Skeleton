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
    if value != value.strip():
        raise ValueError(f"runtime outcome event {field_name} must be normalized")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _require_sha256(value: object, field_name: str) -> str:
    digest = _require_text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX_DIGITS for character in digest):
        raise ValueError(
            f"runtime outcome event {field_name} must be a lowercase SHA-256 digest"
        )
    return digest


def _parse_aware_timestamp(value: object, field_name: str) -> datetime:
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
    return parsed.astimezone(timezone.utc)


def _require_aware_timestamp(value: object, field_name: str) -> str:
    return _parse_aware_timestamp(value, field_name).isoformat()


def _require_runtime_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"execution {field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("execution timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def execution_result_to_event(result: ExecutionResult) -> DomainEvent:
    """Convert one canonical runtime result into a provenance-bound event.

    The producer boundary verifies that the result's provenance still describes
    the actual runtime artifact before minting the durable execution identity.
    """

    if result.provenance is None:
        raise ValueError("execution result requires provenance before publication")

    agent = _require_text(result.agent, "agent")
    task = _require_text(result.task, "task")
    started = _require_runtime_datetime(result.started_at, "started_at")
    finished = _require_runtime_datetime(result.finished_at, "finished_at")
    if finished < started:
        raise ValueError("execution finished_at must not precede started_at")

    expected_operation = (
        "agent.execute.completed" if result.succeeded else "agent.execute.failed"
    )
    if result.provenance.operation != expected_operation:
        raise ValueError("execution provenance operation disagrees with result state")

    artifact_sha256 = _require_sha256(
        result.provenance.content_sha256,
        "provenance.content_sha256",
    )
    expected_artifact = stable_content_digest(
        result.output
        if result.succeeded
        else {"task": task, "agent": agent, "error": result.error}
    )
    if artifact_sha256 != expected_artifact:
        raise ValueError("execution provenance artifact digest does not match result")

    source_repository = _require_text(
        result.provenance.source_repository,
        "provenance.source_repository",
    )
    _optional_text(result.provenance.source_revision, "provenance.source_revision")
    _optional_text(result.provenance.source_path, "provenance.source_path")

    provenance_metadata = result.provenance.metadata
    if not isinstance(provenance_metadata, Mapping):
        raise TypeError("execution provenance metadata must be a mapping")
    metadata_agent = _require_text(provenance_metadata.get("agent"), "provenance.metadata.agent")
    metadata_task = _require_text(provenance_metadata.get("task"), "provenance.metadata.task")
    if metadata_agent != agent or metadata_task != task:
        raise ValueError("execution provenance metadata disagrees with runtime result")

    task_sha256 = stable_content_digest(task)
    idempotency_sha256 = provenance_metadata.get("idempotency_key_sha256")
    if idempotency_sha256 is not None:
        idempotency_sha256 = _require_sha256(
            idempotency_sha256,
            "provenance.metadata.idempotency_key_sha256",
        )

    provenance = result.provenance.as_dict()
    # Materialize the already validated source repository so the event cannot
    # accidentally inherit a coercion or whitespace variant from custom input.
    provenance["source_repository"] = source_repository
    identity_material = {
        "agent": agent,
        "task_sha256": task_sha256,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "artifact_sha256": artifact_sha256,
        "idempotency_key_sha256": idempotency_sha256,
        "operation": expected_operation,
    }
    execution_identity = stable_content_digest(identity_material)

    payload: dict[str, Any] = {
        "execution_identity_sha256": execution_identity,
        "agent": agent,
        "succeeded": result.succeeded,
        "task_sha256": task_sha256,
        "artifact_sha256": artifact_sha256,
        "started_at": identity_material["started_at"],
        "finished_at": identity_material["finished_at"],
        "provenance": provenance,
    }
    if idempotency_sha256 is not None:
        payload["idempotency_key_sha256"] = idempotency_sha256
    if result.error is not None:
        payload["error"] = _require_text(result.error, "error")

    return DomainEvent(
        topic="runtime.completed" if result.succeeded else "runtime.failed",
        payload=payload,
        occurred_at=finished,
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
    started = _parse_aware_timestamp(event.payload.get("started_at"), "started_at")
    finished = _parse_aware_timestamp(event.payload.get("finished_at"), "finished_at")
    if finished < started:
        raise ValueError("runtime outcome event finished_at must not precede started_at")
    started_at = started.isoformat()
    finished_at = finished.isoformat()

    if not isinstance(event.occurred_at, datetime):
        raise TypeError("runtime outcome event occurred_at must be a datetime")
    if event.occurred_at.tzinfo is None or event.occurred_at.utcoffset() is None:
        raise ValueError("runtime outcome event occurred_at must be timezone-aware")
    if event.occurred_at.astimezone(timezone.utc) != finished:
        raise ValueError("runtime outcome event occurred_at must equal finished_at")

    operation = _require_text(provenance.get("operation"), "provenance.operation")
    source_repository = _require_text(
        provenance.get("source_repository"),
        "provenance.source_repository",
    )
    source_revision = _optional_text(
        provenance.get("source_revision"),
        "provenance.source_revision",
    )
    source_path = _optional_text(provenance.get("source_path"), "provenance.source_path")
    _require_text(provenance.get("actor"), "provenance.actor")
    _require_aware_timestamp(provenance.get("timestamp"), "provenance.timestamp")

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
    expected_operation = "agent.execute.completed" if succeeded else "agent.execute.failed"
    if operation != expected_operation:
        raise ValueError("runtime outcome event operation disagrees with succeeded state")

    raw_error = event.payload.get("error")
    if succeeded:
        if raw_error is not None:
            raise ValueError("successful runtime outcome event must not contain an error")
    else:
        _require_text(raw_error, "error")

    idempotency_sha256: str | None = None
    raw_idempotency = event.payload.get("idempotency_key_sha256")
    if raw_idempotency is not None:
        idempotency_sha256 = _require_sha256(
            raw_idempotency,
            "idempotency_key_sha256",
        )

    provenance_metadata = provenance.get("metadata")
    if not isinstance(provenance_metadata, Mapping):
        raise TypeError("runtime outcome event provenance metadata must be a mapping")

    provenance_agent = _require_text(
        provenance_metadata.get("agent"),
        "provenance.metadata.agent",
    )
    if provenance_agent != agent:
        raise ValueError("runtime outcome event agent disagrees with provenance")
    provenance_task = _require_text(
        provenance_metadata.get("task"),
        "provenance.metadata.task",
    )
    if stable_content_digest(provenance_task) != task_sha256:
        raise ValueError("runtime outcome event task digest disagrees with provenance")

    provenance_idempotency = provenance_metadata.get("idempotency_key_sha256")
    if provenance_idempotency is not None:
        provenance_idempotency = _require_sha256(
            provenance_idempotency,
            "provenance.metadata.idempotency_key_sha256",
        )
    if provenance_idempotency != idempotency_sha256:
        raise ValueError("runtime outcome event idempotency digest disagrees with provenance")

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
        "source_repository": source_repository,
        "source_revision": source_revision,
        "source_path": source_path,
        "operation": operation,
    }
    if idempotency_sha256 is not None:
        metadata["idempotency_key_sha256"] = idempotency_sha256

    return {
        "id": execution_id,
        "content": f"{event.topic} {agent} {artifact_sha256}",
        "metadata": metadata,
    }
