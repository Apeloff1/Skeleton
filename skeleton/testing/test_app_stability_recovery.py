"""Failure-injection regressions for the existing app health and Windows owners."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from skeleton.app.assembly import ServiceSpec
from skeleton.app.health import probe_http, probe_url, wait_for_application
from skeleton.app.windows_launcher import WindowsLauncher


def test_unconfigured_health_probe_is_not_reported_healthy():
    service = ServiceSpec(
        name="optional", role="tool", path="tools", kind="service",
        public_url="", health_path="",
    )
    observed = probe_url(service)
    assert observed.ok is False
    assert observed.status is None
    assert "no public HTTP health probe" in observed.detail


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), 31])
def test_http_probe_rejects_impossible_timeout_without_sending_request(timeout):
    with pytest.raises(ValueError, match="timeout"):
        probe_http("backend", "http://localhost:8001/api/health", timeout=timeout)


@pytest.mark.parametrize("attempts,timeout,delay", [
    (0, 1, 0), (121, 1, 0), (True, 1, 0),
    (1, 0, 0), (1, float("inf"), 0), (1, float("nan"), 0),
    (1, 1, -1), (1, 1, float("inf")), (1, 1, 31),
])
def test_app_probe_rejects_unbounded_retries_without_network(attempts, timeout, delay):
    with pytest.raises(ValueError):
        wait_for_application(attempts=attempts, timeout=timeout, delay=delay)


class DeadWorker:
    def is_alive(self) -> bool:
        return False


class FakeBrowserServer:
    def __init__(self):
        self.shutdown_calls = 0
        self.close_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1
        raise AssertionError("shutdown() must not be called on a dead serving thread")

    def server_close(self):
        self.close_calls += 1


class FakeOfflineApp:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


def test_windows_launcher_can_reclaim_dead_offline_browser_without_deadlock(tmp_path: Path):
    # Instantiate without tkinter or a real socket; only exercise the
    # existing launcher-owned resource release path.
    launcher = WindowsLauncher.__new__(WindowsLauncher)
    launcher._browser_lock = threading.RLock()
    server = FakeBrowserServer()
    app = FakeOfflineApp()
    token = tmp_path / "browser-failure.secret"
    token.write_text("ephemeral fake fixture", encoding="utf-8")
    launcher._browser_server = server
    launcher._browser_app = app
    launcher._browser_worker = DeadWorker()
    launcher._browser_token_file = token

    result = launcher._stop_browser_service()
    assert "stopped" in result.lower()
    assert server.shutdown_calls == 0
    assert server.close_calls == 1
    assert app.close_calls == 1
    assert not token.exists()
    assert launcher._browser_server is None

    # Retry/cleanup must be safe and idempotent.
    assert "not running" in launcher._stop_browser_service().lower()
