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
        (3, 700.0, 700.0, True, "/api/health/", 200),
        (3, 700.0, 700.0, True, "/api/health/reliability", 200),
        (3, 700.0, 700.0, True, "/api/healthcheck", 503),
        (3, 700.0, 700.0, True, "/api/readiness-bypass", 503),
        (3, 700.0, 700.0, True, "/api/liveness-bypass", 503),
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
        patch.object(build_watchdog, "_watchdog_task", None),
        patch.object(build_watchdog, "_stopped", False),
        patch.object(build_watchdog, "_tick_count", ticks),
        patch.object(build_watchdog, "_first_tick_started_at", first_start),
        patch.object(build_watchdog, "_last_tick_at", last_completed),
        patch.object(reliability.time, "time", return_value=1000.0),
    ):
        response = asyncio.run(middleware.dispatch(_request(app, path), permitted))
    assert response.status_code == expected
    if expected == 503:
        # A reliability rejection is not an auth failure or an upstream 503.
        # Clients must not cache it and must receive bounded retry guidance.
        assert response.headers["retry-after"] == "5"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-skeleton-rejection-source"] == "load-shedding"
        assert response.body == b'{"error":"service_unavailable","reason":"load_shedding"}'
    else:
        assert "x-skeleton-rejection-source" not in response.headers


@pytest.mark.parametrize(
    ("worker_done", "stopped", "scheduled_at", "expected"),
    [
        (None, False, 0.0, 200),   # Watchdog not started.
        (False, False, 1000.0, 200),  # Live first-tick grace.
        (False, False, 800.0, 503),   # Never-executed task exceeded grace.
        (False, False, 0.0, 503),     # Task with no scheduling evidence.
        (True, False, 1000.0, 503),  # Crashed task.
        (False, True, 1000.0, 503),  # Explicitly stopped task.
        (True, True, 1000.0, 503),
    ],
)
def test_worker_task_state_is_a_fail_closed_admission_boundary(
    worker_done: bool | None, stopped: bool, scheduled_at: float, expected: int
) -> None:
    app = FastAPI()
    middleware = reliability.LoadSheddingMiddleware(app, wd_stale_sec=180.0)

    class FakeTask:
        def done(self) -> bool:
            return bool(worker_done)

    task = None if worker_done is None else FakeTask()

    async def permitted(_request: Request) -> Response:
        return Response("ok", status_code=200)

    with (
        patch.object(build_watchdog, "_watchdog_task", task),
        patch.object(build_watchdog, "_stopped", stopped),
        patch.object(build_watchdog, "_watchdog_scheduled_at", scheduled_at),
        patch.object(build_watchdog, "_tick_count", 0),
        patch.object(build_watchdog, "_first_tick_started_at", 0.0),
        patch.object(build_watchdog, "_last_tick_at", 0.0),
        patch.object(reliability.time, "time", return_value=1000.0),
    ):
        response = asyncio.run(middleware.dispatch(_request(app), permitted))
    assert response.status_code == expected
    if expected == 503:
        assert response.headers["x-skeleton-rejection-source"] == "load-shedding"


def test_first_watchdog_tick_has_start_timestamp_before_admission_count() -> None:
    import inspect

    source = inspect.getsource(build_watchdog._scan_once)
    start = source.index("_first_tick_started_at = time.time()")
    admitted = source.index("_tick_count += 1")
    assert start < admitted


def test_watchdog_restart_refreshes_heartbeat_without_resetting_recovery_budget() -> None:
    """An old, stopped task cannot poison the next worker's admission epoch."""

    async def exercise() -> None:
        app = FastAPI()
        app.state._shedding = False
        middleware = reliability.LoadSheddingMiddleware(app, wd_stale_sec=180.0)
        history = [900.0, 950.0]

        async def parked_worker() -> None:
            await asyncio.Event().wait()

        async def permitted(_request: Request) -> Response:
            return Response("ok", status_code=200)

        with (
            patch.object(build_watchdog, "_watchdog_task", None),
            patch.object(build_watchdog, "_stopped", True),
            patch.object(build_watchdog, "_tick_count", 7),
            patch.object(build_watchdog, "_first_tick_started_at", 100.0),
            patch.object(build_watchdog, "_last_tick_at", 100.0),
            patch.object(build_watchdog, "_last_counts", {"scanned": 3}),
            patch.object(build_watchdog, "_restart_history", history),
            patch.object(build_watchdog, "_watchdog_scheduled_at", 100.0),
            patch.object(build_watchdog, "_loop", parked_worker),
        ):
            build_watchdog.start_watchdog()
            task = build_watchdog._watchdog_task
            assert task is not None
            try:
                # This is a new task, not a new recovery budget.
                assert build_watchdog._tick_count == 0
                assert build_watchdog._first_tick_started_at == 0.0
                assert build_watchdog._last_tick_at == 0.0
                assert build_watchdog._watchdog_scheduled_at > 100.0
                assert build_watchdog._last_counts == {}
                assert build_watchdog._restart_history is history
                assert build_watchdog._stopped is False

                # Compare against the actual newly recorded scheduling epoch.
                with patch.object(reliability.time, "time", return_value=build_watchdog._watchdog_scheduled_at):
                    response = await middleware.dispatch(_request(app), permitted)
                assert response.status_code == 200

                # Re-admitting the already-running task must retain its state.
                build_watchdog._tick_count = 5
                build_watchdog._last_tick_at = 950.0
                original_scheduled = build_watchdog._watchdog_scheduled_at
                build_watchdog.start_watchdog()
                assert build_watchdog._watchdog_task is task
                assert build_watchdog._tick_count == 5
                assert build_watchdog._last_tick_at == 950.0
                assert build_watchdog._watchdog_scheduled_at == original_scheduled
                assert build_watchdog._restart_history == history
            finally:
                build_watchdog.stop_watchdog()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    asyncio.run(exercise())
