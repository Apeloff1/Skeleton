"""Reusable gated fixtures for app-foundation HTTP tests.

``gated_client`` builds the REAL ``skeleton.api.server.create_app()`` (install_gate
included), points AppServices at a temp dir, mints a real ``x-gf-seal`` with
``mint_seal`` and logs a user in for a Bearer session.  Import from other test
packages with ``pytest_plugins = ["tests.app_services.conftest"]``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pytest

SEAL_SECRET = "test-gated-seal-secret"


@dataclass
class GatedClient:
    client: Any
    services: Any
    headers: dict = field(default_factory=dict)     # seal + session (+ x-request-id)
    seal_only: dict = field(default_factory=dict)   # seal, no session
    user: Any = None
    new_session: Callable[[str, str], dict] = None  # (email, password) -> full headers


@pytest.fixture
def app_services(tmp_path):
    from skeleton.app_services.container import AppServices
    svc = AppServices.open(tmp_path / "app")
    yield svc
    svc.close()


@pytest.fixture
def gated_client(app_services, monkeypatch):
    from fastapi.testclient import TestClient

    from skeleton.api.hmac_seal import mint_seal
    from skeleton.app_services import job_api, runtime

    monkeypatch.setenv("GF_SEAL_SECRET", SEAL_SECRET)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    monkeypatch.setattr(runtime, "_services", app_services)
    job_api.set_job_service(app_services.jobs)
    from skeleton.api.server import create_app
    app = create_app()
    client = TestClient(app)  # no context manager: skips startup/lifespan (Walt's)
    from skeleton.kernel import runtime_supervision  # noqa: F401
    lifecycle = getattr(app.state, "runtime_lifecycle", None)
    if lifecycle is not None and hasattr(lifecycle, "mark_ready"):
        lifecycle.mark_ready(reason="test")

    def new_session(email: str, password: str) -> dict:
        if app_services.auth.users.find_by_email(email) is None:
            app_services.auth.register(email, password)
        token = app_services.auth.login(email, password).token
        return {"x-gf-seal": mint_seal("test-sdk", 300), "Authorization": f"Bearer {token}"}

    headers = new_session("gated@example.com", "gated-password-1")
    user = app_services.auth.users.find_by_email("gated@example.com")[0]
    yield GatedClient(client=client, services=app_services, headers=headers,
                      seal_only={"x-gf-seal": headers["x-gf-seal"]}, user=user, new_session=new_session)
    job_api.set_job_service(None)
