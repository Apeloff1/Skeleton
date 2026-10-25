"""Watchdog startup admission must not trigger false load shedding.

Regression for App Foundation E2E run 40116545623: the authorized /me call
returned 200, then the immediately following anonymous /me call returned 503
when the first watchdog sweep began. A started first tick is not a stale tick.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from starlette.requests import Request

from core import build_watchdog, reliability


def _request(app: FastAPI, path: str = "/api/auth/me") -> Request:
    return Request(
        {
            "type": "http",
            "app": app,
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.parametrize(
    ("ticks", "first_start", "last_completed", "draining", "path", "expected"),
    [
        (0, 0.0, 0.0, False, "/api/auth/me", 200),
        (1, 1000.0, 0.0, False, "/api/auth/me", 200),
        (1, 1000.0, 0.0, False, "/api/galaxy-studio/status/one", 200),
        (1, 800.0, 0.0, False, "/api/auth/me", 503),
        (1, 0.0, 0.0, False, "/api/auth/me", 503),
        (3, 1000.0, 900.0, False, "/api/auth/me", 200),
        (3, 1000.0, 800.0, False, "/api/auth/me", 503),
        (3, 1000.0, 0.0, True, "/api/auth/me", 503),
        (3, 700.0, 700.0, True, "/api/health", 200),
    ],
)
def test_watchdog_sheds_only_stale_or_draining_requests(
    ticks: int,
    first_start: float,
    last_completed: float,
    draining: bool,
    path: str,
    expected: int,
) -> None:
    app = FastAPI()
    app.state._shedding = draining
    middleware = reliability.LoadSheddingMiddleware(app, wd_stale_sec=180.0)

    async def permitted(_request: Request) -> Response:
        return Response("ok", status_code=200)

    with (
        patch.object(build_watchdog, "_tick_count", ticks),
        patch.object(build_watchdog, "_first_tick_started_at", first_start),
        patch.object(build_watchdog, "_last_tick_at", last_completed),
        patch.object(reliability.time, "time", return_value=1000.0),
    ):
        response = asyncio.run(middleware.dispatch(_request(app, path), permitted))
    assert response.status_code == expected


def test_first_watchdog_tick_has_start_timestamp_before_admission_count() -> None:
    import inspect

    source = inspect.getsource(build_watchdog._scan_once)
    start = source.index("_first_tick_started_at = time.time()")
    admitted = source.index("_tick_count += 1")
    assert start < admitted
