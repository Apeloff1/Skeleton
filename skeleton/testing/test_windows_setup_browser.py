"""Windows setup browser must remain usable during protected backend failure.

These tests verify only the launcher admission boundary. They do not claim
Windows, Docker, guarded inference, or real-device qualification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.app.health import ProbeResult
from skeleton.app import windows_launcher as launcher


def _probe(ok: bool, *, status: int | None = 200, detail: str = "healthy") -> ProbeResult:
    return ProbeResult(
        service="frontend", url="http://localhost:3456/", ok=ok,
        status=status, detail=detail,
    )


def test_setup_opens_when_backend_and_guard_are_unavailable(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("opening setup must not require whole-application readiness")

    monkeypatch.setattr(launcher, "runtime_status", forbidden)
    monkeypatch.setattr(
        launcher, "public_service_urls",
        lambda root, *, manifest: {"frontend": "http://localhost:3456"},
    )
    observed = []
    def probe(service, *, timeout):
        observed.append((service.name, service.public_url, service.health_path, timeout))
        return _probe(True)
    monkeypatch.setattr(launcher, "probe_url", probe)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: observed.append(url) or True)

    ok, detail = launcher.open_running_application(tmp_path)
    assert ok is True
    assert observed[0] == ("frontend", "http://localhost:3456", "/", 2.0)
    assert observed[1] == "http://localhost:3456"
    assert "NOT established" in detail


@pytest.mark.parametrize(
    ("status", "detail"),
    [(None, "URLError: health endpoint unreachable"),
     (503, "HTTP error 503"),
     (200, "health endpoint redirected")],
)
def test_setup_never_opens_browser_for_unhealthy_or_redirected_frontend(
    tmp_path, monkeypatch, status, detail,
):
    monkeypatch.setattr(launcher, "probe_url", lambda *args, **kwargs: _probe(False, status=status, detail=detail))
    monkeypatch.setattr(
        launcher.webbrowser, "open",
        lambda url: pytest.fail("unhealthy frontend must never launch browser"),
    )
    ok, message = launcher.open_running_application(tmp_path)
    assert not ok
    assert "Setup UI unavailable" in message


@pytest.mark.parametrize(
    "address",
    [
        "https://outside.example:3456",
        "http://outside.example:3456",
        "http://user:pass@localhost:3456",
        "http://localhost:3456/setup?token=private",
        "http://localhost:not-a-port",
    ],
)
def test_setup_rejects_nonlocal_or_credential_bearing_browser_targets(
    tmp_path, monkeypatch, address,
):
    monkeypatch.setattr(
        launcher, "public_service_urls",
        lambda root, *, manifest: {"frontend": address},
    )
    monkeypatch.setattr(
        launcher, "probe_url",
        lambda *args, **kwargs: pytest.fail("invalid target must not be probed"),
    )
    monkeypatch.setattr(
        launcher.webbrowser, "open",
        lambda url: pytest.fail("invalid target must not launch browser"),
    )
    ok, detail = launcher.open_running_application(tmp_path)
    assert not ok
    assert "private" not in detail
    assert "pass" not in detail


def test_browser_refusal_is_not_misreported_as_application_readiness(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(launcher, "probe_url", lambda *args, **kwargs: _probe(True))
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: False)
    ok, detail = launcher.open_running_application(tmp_path)
    assert not ok
    assert "no browser accepted" in detail
