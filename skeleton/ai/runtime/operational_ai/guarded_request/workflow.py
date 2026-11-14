"""Capacity gate around the *real* OfflineAIService, never a model replacement.

This queue is in-process only; the underlying OfflineAIService owns cross-
process session fencing, native model generation, durable replay and audit.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any

from .budgets import Quota
from .contracts import require_text
from .errors import deny
from .identities import Scope, require_id
from .pressure import Pressure, PressurePolicy
from .queue import FairQueue, QueueTicket


@dataclass(frozen=True, slots=True)
class NativeRequest:
    scope: Scope
    request_id: str
    question: str

    def __post_init__(self) -> None:
        if type(self.scope) is not Scope:
            deny("request-scope")
        require_id(self.request_id, "request")
        require_text(self.question, maximum=32768, field="question")


class GuardedDispatcher:
    """Fair scheduling into the authoritative native inference service.

    No autonomous retries: a failed service call propagates the exception.
    A response is never fabricated by this layer.
    """

    def __init__(
        self,
        service: Any,
        *,
        quota: Quota | None = None,
        queue: FairQueue | None = None,
        pressure_policy: PressurePolicy | None = None,
    ):
        if not callable(getattr(service, "turn", None)) or not hasattr(service, "actor"):
            deny("native-service-required")
        self.service = service
        self.quota = quota or Quota()
        self.queue = queue or FairQueue()
        self.pressure_policy = pressure_policy or PressurePolicy()
        self._lock = RLock()
        self._requests: dict[str, NativeRequest] = {}

    def submit(self, request: NativeRequest, *, pressure: Pressure, now_mono_ms: int) -> str:
        if type(request) is not NativeRequest:
            deny("request-type")
        if request.scope.tenant != self.service.actor.tenant or request.scope.user != self.service.actor.user:
            deny("service-owner")
        if request.scope.model_digest != self.service.actor.model_digest:
            deny("service-model")
        if len(request.question.encode("utf-8")) > self.quota.input_bytes:
            deny("question-bytes")
        disposition = self.pressure_policy.decide(pressure, now_mono_ms)
        with self._lock:
            ticket = QueueTicket(request.request_id, request.scope.tenant)
            self.queue.enqueue(ticket)
            self._requests[request.request_id] = request
        return disposition

    def drain_one(self) -> Any | None:
        with self._lock:
            ticket = self.queue.poll()
            if ticket is None:
                return None
            request = self._requests[ticket.request_id]
        try:
            response = self.service.turn(
                session=request.scope.session,
                request_id=request.request_id,
                question=request.question,
            )
            # The underlying native model gateway must itself bound output before commit.
            # A post-commit limit cannot roll back a durable chat turn.
            return response
        finally:
            with self._lock:
                del self._requests[ticket.request_id]
                self.queue.finish(ticket)

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            cancelled = self.queue.cancel(request_id)
            if cancelled:
                del self._requests[request_id]
            return cancelled
