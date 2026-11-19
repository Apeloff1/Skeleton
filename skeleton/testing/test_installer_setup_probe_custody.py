"""Deterministic installer setup-route probe failure custody."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from skeleton.app.installer import _probe_setup_route


@dataclass(frozen=True)
class Frontend:
    public_url: str = "http://127.0.0.1:3000"
    health_path: str = "/health"


@pytest.mark.parametrize("error", [OSError, ValueError, TypeError, KeyError, TimeoutError])
def test_setup_probe_failures_are_nonfatal_and_redacted(monkeypatch, error):
    import skeleton.app.health as health

    def broken_probe(service, *, timeout):
        raise error("sensitive-token-must-not-escape")

    monkeypatch.setattr(health, "probe_local_setup", broken_probe)
    assert _probe_setup_route(Frontend(), "http://127.0.0.1:3000") is False


@pytest.mark.parametrize("available", [True, False])
def test_setup_probe_preserves_explicit_availability(monkeypatch, available):
    import skeleton.app.health as health
    seen = []

    def probe(service, *, timeout):
        seen.append((service.public_url, service.health_path, timeout))
        return SimpleNamespace(ok=available)

    monkeypatch.setattr(health, "probe_local_setup", probe)
    assert _probe_setup_route(Frontend(), "http://127.0.0.1:3000") is available
    assert seen == [("http://127.0.0.1:3000", "/setup", 2.0)]
