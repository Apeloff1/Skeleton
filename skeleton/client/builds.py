"""Builds client over engine executions.

Backend: ``skeleton/api/engine_routes.py`` (``/engine`` prefix, mounted under
``/api/v1``). Engine routes require ``Authorization: Bearer <service token>``
and ``X-Zaibatsu-Attester`` headers; pass them via ``GatewayClient(headers=...)``
or :meth:`BuildsClient.service_headers`.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterator, Mapping, TypedDict
from urllib.parse import quote

from skeleton.client.cancel import CancelToken
from skeleton.client.gateway import GatewayClient
from skeleton.client.streaming import StreamEvent, stream_events

# GET /api/v1/events (canonical realtime stream, #4128) is declared in
# skeleton.client.events.SDK_ROUTES; stream_events uses it via skeleton.client.realtime.

SDK_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/v1/engine/executions"),
    ("GET", "/api/v1/engine/executions/{execution_id}"),
    ("GET", "/api/v1/engine/executions/{execution_id}/handoff"),
    ("POST", "/api/v1/engine/executions/{execution_id}/cancel"),
    ("GET", "/api/v1/engine/executions/{execution_id}/events"),
)

TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


class BuildAck(TypedDict, total=False):
    """``EngineExecutionAck.as_dict()``."""

    schema_version: str
    operation_id: str
    execution_id: str
    state: str
    accepted_at: str
    idempotency_digest: str
    status_ref: str
    events_ref: str
    trace_id: str


class BuildEventsSnapshot(TypedDict):
    execution_id: str
    events: list[dict[str, Any]]
    next_sequence: int


def _seg(value: str) -> str:
    return quote(value, safe="")


class BuildsClient:
    """Typed client for engine executions ("builds"), scoped to actor/tenant."""

    def __init__(self, gateway: GatewayClient, *, actor_id: str, tenant_id: str) -> None:
        if not actor_id or not tenant_id:
            raise ValueError("actor_id and tenant_id are required")
        self._gw = gateway
        self.actor_id = actor_id
        self.tenant_id = tenant_id

    @staticmethod
    def service_headers(service_token: str, attester: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {service_token}", "X-Zaibatsu-Attester": attester}

    def _scope(self) -> dict[str, str]:
        return {"actor_id": self.actor_id, "tenant_id": self.tenant_id}

    def submit(self, command: Mapping[str, Any]) -> BuildAck:
        """POST /engine/executions (202). Not retried (non-idempotent)."""
        return self._gw._json(
            "POST", "/api/v1/engine/executions",
            json={**self._scope(), "command": dict(command)},
        )

    def status(self, execution_id: str, *, cancel: CancelToken | None = None) -> dict[str, Any]:
        return self._gw._json(
            "GET", f"/api/v1/engine/executions/{_seg(execution_id)}",
            params=self._scope(), idempotent=True, cancel=cancel,
        )

    def handoff(self, execution_id: str) -> dict[str, Any]:
        return self._gw._json(
            "GET", f"/api/v1/engine/executions/{_seg(execution_id)}/handoff",
            params=self._scope(), idempotent=True,
        )

    def cancel(self, execution_id: str, reason: str = "cancelled by client") -> dict[str, Any]:
        """POST /engine/executions/{id}/cancel — server-side cancellation."""
        return self._gw._json(
            "POST", f"/api/v1/engine/executions/{_seg(execution_id)}/cancel",
            json={**self._scope(), "reason": reason},
        )

    def events(self, execution_id: str) -> BuildEventsSnapshot:
        """GET /engine/executions/{id}/events — JSON snapshot (current backend)."""
        return self._gw._json(
            "GET", f"/api/v1/engine/executions/{_seg(execution_id)}/events",
            params=self._scope(), idempotent=True,
        )

    def stream_events(
        self,
        execution_id: str,
        cancel: CancelToken | None = None,
        *,
        last_event_id: str | None = None,
        cursor: str | None = None,
        channels: tuple[str, ...] = ("build", "agent"),
        transport: Any = None,
        http_client: Any = None,
        on_reset: Callable[[Any], Any] | None = None,
        realtime_options: Mapping[str, Any] | None = None,
    ) -> Iterator[StreamEvent]:
        """Live events for one execution from the canonical ``GET /api/v1/events``.

        Delegates to ``skeleton.client.realtime.RealtimeClient`` (#4128) through
        :func:`skeleton.client.events.stream_realtime`, filtered server-side with
        ``?job_id=<execution_id>`` with required actor/tenant scope and the
        GatewayClient bearer service credential. Resumes
        from ``last_event_id`` (or ``cursor``; #4140 sends it as Last-Event-ID and ``?cursor=``),
        reconnects with jittered backoff, and yields ``stream.reset`` /
        ``stream.lagged`` control events. Runs until ``cancel`` fires or the
        generator is closed. Seal: the gateway's ``x-gf-seal`` per connect.
        """
        from skeleton.client.events import stream_realtime
        if not execution_id:
            raise ValueError("execution_id is required")
        return stream_realtime(
            self._gw, channels=channels, job_id=execution_id,
            actor_id=self.actor_id, tenant_id=self.tenant_id,
            last_event_id=last_event_id, cursor=cursor, cancel=cancel,
            transport=transport, http_client=http_client, on_reset=on_reset,
            realtime_options=realtime_options,
        )
    def stream_execution_events(
        self,
        execution_id: str,
        cancel: CancelToken | None = None,
        *,
        last_event_id: str | None = None,
        cursor: str | None = None,
    ):
        """One-shot read of the per-execution filtered view.

        GET /api/v1/engine/executions/{id}/events (SSE when the hub is
        mounted, otherwise today's JSON snapshot). No reconnect. This is the
        pre-#4128 stream_events behaviour, kept for snapshot-style callers.

        PROVISIONAL: the transport is pending Walt's realtime decision and
        will delegate to skeleton/client/realtime.
        Yields SSE v1 envelopes, or the events of today's JSON snapshot.
        Resume uses last_event_id (sent as the Last-Event-ID header) or
        cursor (sent as ?cursor=). It does not reconnect.
        """
        return stream_events(
            self._gw, f"/api/v1/engine/executions/{_seg(execution_id)}/events",
            params=self._scope(), last_event_id=last_event_id, cursor=cursor,
            cancel=cancel, idempotent=True,
        )

    def wait(
        self,
        execution_id: str,
        *,
        poll_seconds: float = 1.0,
        timeout_seconds: float = 600.0,
        cancel: CancelToken | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> dict[str, Any]:
        """Poll status until a terminal ``execution_state``/``state``."""
        from skeleton.client.errors import SkeletonTimeoutError

        if timeout_seconds is None or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive number (default 600)")
        nap = sleep or self._gw._sleep
        deadline = clock() + timeout_seconds
        while True:
            if cancel is not None:
                cancel.raise_if_cancelled()
            current = self.status(execution_id, cancel=cancel)
            state = current.get("execution_state", current.get("state"))
            if state in TERMINAL_STATES:
                return current
            if clock() >= deadline:
                raise SkeletonTimeoutError(f"build {execution_id} not terminal (state={state})")
            if cancel is not None and nap is time.sleep:
                cancel.wait(poll_seconds)
            else:
                nap(poll_seconds)
