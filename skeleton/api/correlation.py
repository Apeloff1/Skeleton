"""API request correlation helpers for canonical runtime execution.

The functions stay framework-light: any request object exposing ``headers`` and
``state`` can participate. A valid existing request-state identifier wins,
otherwise exactly one valid ``X-Request-ID`` is accepted; malformed or duplicate
header values fail closed to a server-generated identifier.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping
from typing import Any

from skeleton.frontier.model_runtime import CancellationToken
from skeleton.frontier.orchestration import OrchestrationDriver, RunRecord, ToolCapability
from skeleton.observability.orchestration import ObservableOrchestrator


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _valid_request_id(value: object) -> str | None:
    if isinstance(value, str) and _REQUEST_ID_RE.fullmatch(value):
        return value
    return None


def request_correlation_id(request: object) -> str:
    """Resolve and persist one safe request correlation identifier."""
    state = getattr(request, "state", None)
    state_id = _valid_request_id(getattr(state, "request_id", None))
    if state_id is not None:
        return state_id

    headers = getattr(request, "headers", None)
    candidates: list[str] = []
    getlist = getattr(headers, "getlist", None)
    if callable(getlist):
        values = getlist("x-request-id")
        if isinstance(values, list):
            candidates = [value for value in values if isinstance(value, str)]
    elif isinstance(headers, Mapping):
        raw = headers.get("x-request-id") or headers.get("X-Request-ID")
        if isinstance(raw, str):
            candidates = [raw]

    resolved = (
        _valid_request_id(candidates[0])
        if len(candidates) == 1
        else None
    ) or secrets.token_hex(16)

    if state is not None:
        try:
            setattr(state, "request_id", resolved)
        except (AttributeError, TypeError):
            pass
    return resolved


async def run_with_request_correlation(
    orchestrator: ObservableOrchestrator,
    request: object,
    driver: OrchestrationDriver,
    *,
    cancellation: CancellationToken | None = None,
    run_id: str | None = None,
    capabilities: tuple[ToolCapability | str, ...] = (),
) -> RunRecord:
    """Run canonical orchestration with the API request correlation attached."""
    correlation_id = request_correlation_id(request)
    return await orchestrator.run(
        driver,
        cancellation=cancellation,
        run_id=run_id,
        capabilities=capabilities,
        correlation_id=correlation_id,
    )
