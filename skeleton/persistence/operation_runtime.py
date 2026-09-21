"""Durable production binding for reasoning operations.

The IntelligenceOrchestrator remains the reasoning engine. This facade owns the
production operation lifecycle:

OperationEnvelope -> SQLiteOperationStore (authority)
                  -> transactional outbox
                  -> SQLiteOperationEventStore (resumable projection)

State commits are authoritative. Stream publication is retryable: if delivery
fails after a state transition, the outbox row remains pending and is drained on
startup or a later dispatch. This prevents the transport from becoming the
owner of operation truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from skeleton.config.settings import OperationSettings
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_store import (
    OperationStoreError,
    SQLiteOperationStore,
    StoredOperation,
)


@dataclass(frozen=True, slots=True)
class OutboxDispatchReport:
    attempted: int
    published: int
    remaining: int
    error_type: str | None = None

    @property
    def healthy(self) -> bool:
        return self.error_type is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "published": self.published,
            "remaining": self.remaining,
            "error_type": self.error_type,
            "healthy": self.healthy,
        }


class DurableOperationRuntime:
    """Durable facade around the existing reasoning orchestrator."""

    def __init__(
        self,
        orchestrator: Any,
        operations: SQLiteOperationStore,
        stream: SQLiteOperationEventStore,
        *,
        outbox_batch_size: int = 256,
        default_deadline_s: float = 120.0,
    ) -> None:
        if orchestrator is None or not callable(getattr(orchestrator, "reason", None)):
            raise TypeError("orchestrator must expose reason()")
        if isinstance(outbox_batch_size, bool) or not isinstance(outbox_batch_size, int):
            raise TypeError("outbox_batch_size must be an integer")
        if outbox_batch_size < 1:
            raise ValueError("outbox_batch_size must be positive")
        if not isinstance(default_deadline_s, (int, float)) or isinstance(
            default_deadline_s, bool
        ):
            raise TypeError("default_deadline_s must be numeric")
        if float(default_deadline_s) <= 0:
            raise ValueError("default_deadline_s must be positive")

        self.orchestrator = orchestrator
        self.operations = operations
        self.stream = stream
        self.outbox_batch_size = outbox_batch_size
        self.default_deadline_s = float(default_deadline_s)
        self._closed = False
        self._dispatch_failures = 0
        self._last_dispatch: OutboxDispatchReport | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.orchestrator, name)

    @classmethod
    def from_settings(
        cls,
        orchestrator: Any,
        settings: OperationSettings,
    ) -> "DurableOperationRuntime":
        state_path = Path(settings.state_path)
        stream_path = Path(settings.stream_path)
        if str(state_path) != ":memory:":
            state_path.parent.mkdir(parents=True, exist_ok=True)
        if str(stream_path) != ":memory:":
            stream_path.parent.mkdir(parents=True, exist_ok=True)
        return cls(
            orchestrator,
            SQLiteOperationStore(state_path),
            SQLiteOperationEventStore(stream_path),
            outbox_batch_size=settings.outbox_batch_size,
            default_deadline_s=settings.default_deadline_s,
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def dispatch_outbox(
        self,
        *,
        operation_id: str | None = None,
        limit: int | None = None,
    ) -> OutboxDispatchReport:
        """Publish pending outbox rows to the canonical durable stream."""
        batch = self.outbox_batch_size if limit is None else limit
        pending = self.operations.pending_outbox(
            operation_id=operation_id,
            limit=batch,
        )
        published = 0
        error_type: str | None = None

        for item in pending:
            try:
                self.stream.append(
                    item.operation_id,
                    item.event_type,
                    dict(item.payload),
                    event_id=item.outbox_id,
                    timestamp=item.created_at,
                )
                self.operations.acknowledge_outbox(item.outbox_id)
                published += 1
            except Exception as exc:
                self._dispatch_failures += 1
                error_type = type(exc).__name__
                break

        remaining = len(
            self.operations.pending_outbox(
                operation_id=operation_id,
                limit=self.outbox_batch_size,
            )
        )
        report = OutboxDispatchReport(
            attempted=len(pending),
            published=published,
            remaining=remaining,
            error_type=error_type,
        )
        self._last_dispatch = report
        return report

    def _dispatch_after_commit(self, operation_id: str) -> None:
        self.dispatch_outbox(operation_id=operation_id)

    def _transition(
        self,
        current: StoredOperation,
        target: OperationState,
    ) -> StoredOperation:
        next_state = self.operations.transition(
            current.envelope.operation_id,
            target,
            expected_version=current.version,
        )
        self._dispatch_after_commit(current.envelope.operation_id)
        return next_state

    def reason(
        self,
        query: str,
        context: dict[str, Any] | None = None,
        *,
        min_confidence: float | None = None,
        max_attempts: int | None = None,
        deadline: float | None = None,
        selection_mode: str | None = None,
        use_cache: bool = True,
        tenant_id: str = "system",
        actor_id: str = "api",
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        if self._closed:
            raise OperationStoreError("durable operation runtime is closed")

        now = self._now()
        if deadline is None:
            deadline_at = now + timedelta(seconds=self.default_deadline_s)
        else:
            deadline_at = datetime.fromtimestamp(float(deadline), tz=timezone.utc)
            if deadline_at <= now:
                raise ValueError("deadline must be in the future")

        envelope = OperationEnvelope(
            operation_id=str(uuid4()),
            tenant_id=str(tenant_id).strip() or "system",
            actor_id=str(actor_id).strip() or "api",
            capability="intelligence.reason",
            created_at=now,
            deadline=deadline_at,
            idempotency_key=idempotency_key or str(uuid4()),
            trace_id=trace_id or str(uuid4()),
        )
        current = self.operations.create(envelope, now=now)
        self._dispatch_after_commit(current.envelope.operation_id)

        if current.envelope.operation_id != envelope.operation_id:
            return {
                "operation_id": current.envelope.operation_id,
                "operation_state": current.envelope.state.value,
                "operation_version": current.version,
                "idempotent_replay": True,
                "result_replay_available": False,
            }

        for state in (
            OperationState.VALIDATED,
            OperationState.AUTHORIZED,
            OperationState.ADMITTED,
            OperationState.RUNNING,
        ):
            current = self._transition(current, state)

        try:
            result = self.orchestrator.reason(
                query=query,
                context=context,
                min_confidence=min_confidence,
                max_attempts=max_attempts,
                deadline=deadline,
                selection_mode=selection_mode,
                use_cache=use_cache,
            )
        except Exception:
            self._transition(current, OperationState.FAILED)
            raise

        terminal = (
            OperationState.FAILED
            if isinstance(result, dict) and result.get("error")
            else OperationState.COMPLETED
        )
        current = self._transition(current, terminal)

        payload = dict(result)
        payload.update(
            {
                "operation_id": current.envelope.operation_id,
                "operation_state": current.envelope.state.value,
                "operation_version": current.version,
                "trace_id": current.envelope.trace_id,
                "idempotent_replay": False,
            }
        )
        return payload

    def stats(self) -> dict[str, Any]:
        base = (
            self.orchestrator.stats()
            if callable(getattr(self.orchestrator, "stats", None))
            else {}
        )
        pending = len(
            self.operations.pending_outbox(limit=self.outbox_batch_size)
        )
        return {
            **dict(base),
            "durable_operation_runtime": {
                "closed": self._closed,
                "pending_outbox": pending,
                "dispatch_failures": self._dispatch_failures,
                "last_dispatch": (
                    None
                    if self._last_dispatch is None
                    else self._last_dispatch.as_dict()
                ),
            },
        }

    def close(self) -> None:
        if self._closed:
            return
        self.dispatch_outbox()
        self.operations.close()
        self.stream.close()
        self._closed = True


__all__ = [
    "DurableOperationRuntime",
    "OutboxDispatchReport",
]
