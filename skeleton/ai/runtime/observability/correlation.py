"""Shared correlation context for logs, traces, events, and background jobs.

``ObservableOrchestrator`` and bare ``EventBus.publish`` paths share one
ContextVar so correlation IDs survive API → agent → tool → side-bus hops
without inventing a second plane.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Callable, Dict, Iterator, Optional

from skeleton.kernel.errors import KernelError

_CORRELATION_ID: ContextVar[str] = ContextVar(
    "skeleton_observability_correlation_id",
    default="",
)



class CorrelationError(KernelError):
    code = "OBS.CORRELATION"


def get_correlation_id() -> str:
    """Return the active correlation id, or ``\"\"`` when unset."""

    return _CORRELATION_ID.get() or ""


def set_correlation_id(value: str) -> Token:
    """Bind ``value`` as the active correlation id; return a reset token."""

    if not isinstance(value, str):
        raise TypeError("correlation_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise CorrelationError("correlation_id must not be empty")
    if normalized != value:
        raise CorrelationError("correlation_id must be normalized")
    if len(value) > 128:
        raise CorrelationError(
            "correlation_id must be at most 128 characters",
            context={"length": len(value)},
        )
    return _CORRELATION_ID.set(value)


def reset_correlation_id(token: Token) -> None:
    """Reset the correlation ContextVar using ``token`` from ``set_correlation_id``."""

    _CORRELATION_ID.reset(token)


@contextmanager
def correlation_scope(correlation_id: str | None = None) -> Iterator[str]:
    """Temporarily bind a correlation id (generated when omitted)."""

    effective = correlation_id
    if effective is None:
        effective = uuid.uuid4().hex
    token = set_correlation_id(effective)
    try:
        yield effective
    finally:
        reset_correlation_id(token)


@contextmanager
def background_job(
    name: str,
    *,
    correlation_id: str | None = None,
    emit: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Iterator[str]:
    """Correlate a background job and optionally emit start/finish metadata events.

    ``emit`` receives ``(topic, payload)`` with metadata only — no payloads of
    work items. Failures on ``emit`` are isolated.
    """

    if not isinstance(name, str) or not name.strip():
        raise CorrelationError("job name must be a non-empty string")
    job_name = name.strip()
    started = time.perf_counter()
    with correlation_scope(correlation_id) as cid:
        if emit is not None:
            try:
                emit(
                    "observability.job.started",
                    {
                        "job": job_name,
                        "correlation_id": cid,
                        "status": "running",
                    },
                )
            except Exception:
                pass
        try:
            yield cid
        except Exception as exc:
            if emit is not None:
                try:
                    emit(
                        "observability.job.failed",
                        {
                            "job": job_name,
                            "correlation_id": cid,
                            "status": "failed",
                            "error_type": type(exc).__name__,
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 3
                            ),
                        },
                    )
                except Exception:
                    pass
            raise
        else:
            if emit is not None:
                try:
                    emit(
                        "observability.job.completed",
                        {
                            "job": job_name,
                            "correlation_id": cid,
                            "status": "completed",
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 3
                            ),
                        },
                    )
                except Exception:
                    pass


def install_event_bus_fallback() -> None:
    """Register the ContextVar fallback on ``EventBus.publish`` / ``emit``.

    Registration is deliberately repeatable: tests and embedding runtimes may
    clear the kernel fallback explicitly, and a later install call must restore
    the canonical provider rather than trust stale local state.
    """

    from skeleton.kernel.primitives import register_correlation_fallback

    register_correlation_fallback(get_correlation_id)


# Install on import so observability users get bus inheritance automatically.
install_event_bus_fallback()
