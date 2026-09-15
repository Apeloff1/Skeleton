"""Boundary adapters between runtime execution, durable events and memory.

The runtime, event bus and memory store remain separate canonical primitives.
This module only translates their existing contracts so execution outcomes can
cross durable boundaries without losing provenance or idempotency identity.
"""

from __future__ import annotations

from datetime import timezone
from typing import Any, Mapping

from skeleton.frontier.agent_runtime import ExecutionResult
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent


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
    """Normalize a runtime outcome event into the existing memory contract."""

    if event.topic not in {"runtime.completed", "runtime.failed"}:
        raise ValueError("expected a runtime outcome event")

    execution_id = str(event.payload.get("execution_identity_sha256") or "").strip()
    agent = str(event.payload.get("agent") or "").strip()
    artifact_sha256 = str(event.payload.get("artifact_sha256") or "").strip()
    if not execution_id or not agent or not artifact_sha256:
        raise ValueError(
            "runtime outcome event requires execution identity, agent and artifact digest"
        )

    provenance = event.payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise TypeError("runtime outcome event provenance must be a mapping")

    metadata: dict[str, Any] = {
        "event_topic": event.topic,
        "agent": agent,
        "succeeded": bool(event.payload.get("succeeded")),
        "task_sha256": str(event.payload.get("task_sha256") or ""),
        "artifact_sha256": artifact_sha256,
        "execution_identity_sha256": execution_id,
        "source_repository": str(provenance.get("source_repository") or ""),
        "source_revision": provenance.get("source_revision"),
        "source_path": provenance.get("source_path"),
        "operation": str(provenance.get("operation") or ""),
    }
    idempotency_sha256 = event.payload.get("idempotency_key_sha256")
    if idempotency_sha256 is not None:
        metadata["idempotency_key_sha256"] = str(idempotency_sha256)

    return {
        "id": execution_id,
        "content": f"{event.topic} {agent} {artifact_sha256}",
        "metadata": metadata,
    }
