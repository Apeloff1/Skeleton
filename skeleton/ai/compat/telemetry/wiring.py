"""Opt-in wiring of per-plane telemetry into kernel, agent, and API paths (#121).

:mod:`skeleton.telemetry.planes` provides the spans and metrics. This module
attaches them to the three engine planes without editing the instrumented
code:

* **kernel**: :func:`instrument_kernel_orchestrator` wraps one
  ``skeleton.kernel.orchestrator.Orchestrator`` *instance*'s ``dispatch``.
* **agents**: :func:`instrument_coordinator` wraps one
  ``skeleton.automation.agents.coordination.Coordinator`` *instance*'s
  ``dispatch`` / ``dispatch_async``. :func:`traced` covers any other agent
  callable.
* **api**: :class:`PlaneTelemetryMiddleware` is a pure ASGI middleware and
  :func:`install_plane_telemetry` adds it through ``app.add_middleware``.
  The ``api/server.py`` lifespan is not touched.

Every span uses the single shared :class:`PlaneTelemetry` (no second plane)
and carries the active correlation id from
:mod:`skeleton.observability.correlation`. The API middleware binds that id
from the request seal or ``X-Request-ID``, so one id follows a request from
API to agent to kernel. Nothing is active until a caller opts in.
"""

from __future__ import annotations

import functools
import inspect
import re
import uuid
from contextlib import ExitStack
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, TypeVar

from skeleton.observability.correlation import (
    CorrelationError,
    correlation_scope,
    get_correlation_id,
)
from skeleton.telemetry.planes import ERRORS, PlaneTelemetry, default_plane_telemetry

F = TypeVar("F", bound=Callable[..., Any])

_MARK = "__plane_telemetry_wrapped__"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
HTTP_STATUS = "telemetry.plane.http_status"


def _resolve(telemetry: Optional[PlaneTelemetry]) -> PlaneTelemetry:
    return telemetry if telemetry is not None else default_plane_telemetry()


def _safe_correlation_id(value: Any) -> bool:
    """Correlation metadata is not an allowed transport for credentials."""
    if type(value) is not str or not _REQUEST_ID_RE.fullmatch(value):
        return False
    from skeleton.observability.redaction import redact_text
    from skeleton.sandbox.sanitizers import redact_secrets

    if redact_text(value) != value:
        return False
    cleaned, kinds = redact_secrets(value)
    return not kinds and cleaned == value


def _bind_correlation(stack: ExitStack, candidate: Any) -> None:
    """Bind ``candidate`` as the correlation id when none is active and it is valid."""

    existing = get_correlation_id()
    if _safe_correlation_id(existing):
        return
    if existing or _safe_correlation_id(candidate):
        try:
            stack.enter_context(correlation_scope(candidate if _safe_correlation_id(candidate) else None))
        except CorrelationError:
            return


def traced(
    plane: str,
    operation: str,
    *,
    telemetry: Optional[PlaneTelemetry] = None,
    **attributes: Any,
) -> Callable[[F], F]:
    """Decorate a sync or async callable so each call emits one plane span."""

    def decorate(fn: F) -> F:
        if getattr(fn, _MARK, None) == (plane, operation):
            return fn

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with _resolve(telemetry).span(plane, operation, **attributes):
                    return await fn(*args, **kwargs)

            setattr(async_wrapper, _MARK, (plane, operation))
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with _resolve(telemetry).span(plane, operation, **attributes):
                return fn(*args, **kwargs)

        setattr(wrapper, _MARK, (plane, operation))
        return wrapper  # type: ignore[return-value]

    return decorate


# ---------------------------------------------------------------------------
# kernel plane
# ---------------------------------------------------------------------------

_KERNEL_RESULT_KEYS = ("runs", "dropped", "n")
_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"})
_TASK_STATES = frozenset({"PENDING", "ASSIGNED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "QUEUED", "IN_PROGRESS"})


def instrument_kernel_orchestrator(orchestrator: Any, *, telemetry: Optional[PlaneTelemetry] = None) -> Any:
    """Emit ``kernel.dispatch`` spans for one orchestrator instance. Idempotent."""

    original = orchestrator.dispatch
    if getattr(original, _MARK, None) == ("kernel", "dispatch"):
        return orchestrator

    @functools.wraps(original)
    def dispatch(*args: Any, **kwargs: Any) -> Any:
        tel = _resolve(telemetry)
        with tel.span("kernel", "dispatch", once=bool(kwargs.get("once", True))) as span:
            result = original(*args, **kwargs)
            if isinstance(result, dict):
                for key in _KERNEL_RESULT_KEYS:
                    value = result.get(key)
                    if type(value) is int and 0 <= value <= 2**53 - 1:
                        span.set_attribute(f"kernel.{key}", value)
                if result.get("kind") == "kernel-orch":
                    span.set_attribute("kernel.kind", "kernel-orch")
                if result.get("reason") == "storm":
                    span.set_attribute("kernel.reason", "storm")
                stages = result.get("trace")
                if isinstance(stages, list):
                    span.set_attribute("kernel.stages", len(stages))
            return result

    setattr(dispatch, _MARK, ("kernel", "dispatch"))
    orchestrator.dispatch = dispatch
    return orchestrator


# ---------------------------------------------------------------------------
# agents plane
# ---------------------------------------------------------------------------


def _task_attrs(span: Any, task: Any) -> None:
    # Only static status categories enter retained spans. Task/agent identifiers,
    # arbitrary descriptions and error details belong to the private task store.
    status = getattr(getattr(task, "status", None), "name", None)
    if type(status) is str and status in _TASK_STATES:
        span.set_attribute("agent.task_status", status)


def _metadata_correlation(args: tuple, kwargs: Dict[str, Any]) -> Any:
    metadata = kwargs.get("metadata")
    if metadata is None and len(args) >= 5:
        metadata = args[4]
    if not isinstance(metadata, dict):
        return None
    for key in ("correlation_id", "request_id", "run_id", "rid"):
        if metadata.get(key):
            return metadata[key]
    return None


def _task_type(args: tuple, kwargs: Dict[str, Any]) -> str:
    value = kwargs.get("task_type", args[1] if len(args) >= 2 else "default")
    return "default" if type(value) is str and value == "default" else "custom"


def instrument_coordinator(coordinator: Any, *, telemetry: Optional[PlaneTelemetry] = None) -> Any:
    """Emit ``agents.execute`` / ``agents.dispatch`` spans for one coordinator. Idempotent.

    When no correlation id is active, a valid ``correlation_id`` / ``request_id``
    / ``run_id`` / ``rid`` from the task metadata is bound for the call, so
    nested kernel spans share it.
    """

    original_async: Callable[..., Awaitable[Any]] = coordinator.dispatch_async
    original_sync: Callable[..., Any] = coordinator.dispatch

    if getattr(original_async, _MARK, None) != ("agents", "execute"):

        @functools.wraps(original_async)
        async def dispatch_async(*args: Any, **kwargs: Any) -> Any:
            tel = _resolve(telemetry)
            with ExitStack() as stack:
                _bind_correlation(stack, _metadata_correlation(args, kwargs))
                with tel.span("agents", "execute", task_type=_task_type(args, kwargs)) as span:
                    task = await original_async(*args, **kwargs)
                    _task_attrs(span, task)
                    return task

        setattr(dispatch_async, _MARK, ("agents", "execute"))
        coordinator.dispatch_async = dispatch_async

    if getattr(original_sync, _MARK, None) != ("agents", "dispatch"):

        @functools.wraps(original_sync)
        def dispatch(*args: Any, **kwargs: Any) -> Any:
            tel = _resolve(telemetry)
            with ExitStack() as stack:
                _bind_correlation(stack, _metadata_correlation(args, kwargs))
                with tel.span("agents", "dispatch", task_type=_task_type(args, kwargs)) as span:
                    task = original_sync(*args, **kwargs)
                    _task_attrs(span, task)
                    return task

        setattr(dispatch, _MARK, ("agents", "dispatch"))
        coordinator.dispatch = dispatch

    return coordinator


# ---------------------------------------------------------------------------
# api plane
# ---------------------------------------------------------------------------


def _header_values(headers: Iterable[Any], name: bytes) -> list[str]:
    values: list[str] = []
    for item in headers or ():
        try:
            key, value = item
        except (TypeError, ValueError):
            continue
        if isinstance(key, (bytes, bytearray)) and key.lower() == name:
            if type(value) is not bytes or len(value) > 128:
                # An invalid occurrence still counts toward duplicate rejection.
                values.append("")
            else:
                values.append(value.decode("latin-1"))
            if len(values) == 2:
                break
    return values


def _scope_request_id(scope: Dict[str, Any]) -> str:
    state = scope.get("state")
    if isinstance(state, dict):
        for attribute in ("seal", "request_id"):
            value = state.get(attribute)
            if _safe_correlation_id(value):
                return value
    supplied = _header_values(scope.get("headers") or (), b"x-request-id")
    # Exactly one well-formed header may seed the id; duplicates fail closed to a minted id.
    candidate = supplied[0] if len(supplied) == 1 else None
    # Preserve the wire contract without an upward dependency on the API layer.
    return candidate if _safe_correlation_id(candidate) else uuid.uuid4().hex[:16]


class PlaneTelemetryMiddleware:
    """Pure ASGI middleware: one ``api.request`` span per HTTP request.

    It binds the request correlation id (an already-active id wins), records the
    response status, counts 5xx responses as plane errors, and echoes
    ``x-request-id`` when the app did not set one. Non-HTTP scopes pass through.
    """

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        *,
        telemetry: Optional[PlaneTelemetry] = None,
        echo_request_id: bool = True,
    ) -> None:
        self.app = app
        self.telemetry = telemetry
        self.echo_request_id = echo_request_id

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        tel = _resolve(self.telemetry)
        raw_method = scope.get("method")
        method = raw_method.upper() if type(raw_method) is str and len(raw_method) <= 8 else "OTHER"
        if method not in _HTTP_METHODS:
            method = "OTHER"
        status_holder: Dict[str, int] = {}

        with ExitStack() as stack:
            existing = get_correlation_id()
            correlation_id = (existing if _safe_correlation_id(existing) else
                              stack.enter_context(correlation_scope(_scope_request_id(scope))))
            state = scope.setdefault("state", {})
            if isinstance(state, dict):
                state["request_id"] = correlation_id

            async def send_wrapper(message: Dict[str, Any]) -> None:
                if message.get("type") == "http.response.start":
                    raw_status = message.get("status")
                    status_holder["status"] = raw_status if type(raw_status) is int and 100 <= raw_status <= 599 else 500
                    if self.echo_request_id:
                        headers = list(message.get("headers") or [])
                        # Keep the wire response and captured span on one
                        # canonical request ID, including duplicate/invalid
                        # downstream response headers. Never echo raw input.
                        headers = [(k, v) for k, v in headers if k.lower() != b"x-request-id"]
                        headers.append((b"x-request-id", correlation_id.encode("ascii")))
                        message = {**message, "headers": headers}
                await send(message)

            # Do not retain raw request paths: user IDs, tokens and source
            # names can appear in path segments even without query strings.
            with tel.span("api", "request", **{"http.method": method}) as span:
                raised = False
                try:
                    await self.app(scope, receive, send_wrapper)
                except BaseException:
                    raised = True
                    raise
                finally:
                    status = status_holder.get("status", 500)
                    if raised and status < 500:
                        span.set_attribute("http.response_interrupted", True)
                    span.set_attribute("http.status_code", status)
                    labels = {"plane": "api", "op": "request", "status": f"{status // 100}xx"}
                    tel.registry.counter(HTTP_STATUS, labels=labels)
                    if status >= 500:
                        span.status = "ERROR"
                        # The span context already counts raised exceptions.
                        if not raised:
                            tel.registry.counter(ERRORS, labels={"plane": "api", "op": "request"})


def install_plane_telemetry(app: Any, *, telemetry: Optional[PlaneTelemetry] = None) -> Any:
    """Opt an ASGI app (FastAPI/Starlette) into API plane telemetry. Idempotent."""

    if getattr(app, "_plane_telemetry_installed", False):
        return app
    app.add_middleware(PlaneTelemetryMiddleware, telemetry=telemetry)
    try:
        setattr(app, "_plane_telemetry_installed", True)
    except (AttributeError, TypeError):
        pass
    return app


__all__ = [
    "HTTP_STATUS",
    "PlaneTelemetryMiddleware",
    "install_plane_telemetry",
    "instrument_coordinator",
    "instrument_kernel_orchestrator",
    "traced",
]
