"""Gate middleware order — sibling of Zaibatsu.Gate Program.cs gauntlet."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api.hmac_seal import mint_seal  # noqa: E402
from skeleton.api.middleware import GatePolicy, install_gate  # noqa: E402
from skeleton.vault.audit import AuditLog  # noqa: E402

SECRET = "gate-middleware-test-secret"


def _app(audit: AuditLog | None = None, policy: GatePolicy | None = None) -> FastAPI:
    app = FastAPI()
    if audit is None:
        audit = AuditLog()
    if policy is None:
        policy = GatePolicy()
    # Routes before middleware so the stack wraps the final router.
    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/ready")
    async def ready():
        return {"status": "up"}

    @app.get("/api/v1/forge/kinds")
    async def kinds():
        return ["source", "sink"]

    @app.post("/api/v1/forge/blueprint")
    async def blueprint():
        return {"status": "created"}

    @app.get("/api/nowhere")
    async def nowhere():
        return {"oops": True}

    install_gate(app, policy=policy, audit_log=audit, max_body_bytes=64)
    return app


@pytest.fixture()
def sealed(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    audit = AuditLog()
    with TestClient(_app(audit=audit)) as c:
        yield c, audit


@pytest.fixture()
def unsealed(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    with TestClient(_app()) as c:
        yield c


def _hdr(attester: str = "gate-bot") -> dict:
    tok = mint_seal(attester, secret=SECRET)
    assert tok
    return {"x-gf-seal": tok}


def test_policy_open_routes():
    p = GatePolicy()
    assert p.is_open_route("/health")
    assert p.is_open_route("/ready")
    assert p.is_open_route("/api/v1/health/ready")
    assert not p.is_open_route("/api/v1/forge/kinds")


def test_policy_domains():
    p = GatePolicy()
    assert p.required_domain("/api/v1/forge/blueprint") == "forge"
    assert p.required_domain("/api/cognition/beliefs") == "cognition"
    assert p.required_domain("/api/nowhere") is None


def test_open_health_without_seal(sealed):
    client, _ = sealed
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    assert "x-request-id" in res.headers


def test_open_ready(sealed):
    client, _ = sealed
    assert client.get("/ready").status_code == 200


def test_protected_missing_seal_401(sealed):
    client, _ = sealed
    res = client.get("/api/v1/forge/kinds")
    assert res.status_code == 401
    assert res.json()["error"] == "invalid_seal"


def test_protected_with_seal_ok(sealed):
    client, audit = sealed
    res = client.get("/api/v1/forge/kinds", headers=_hdr())
    assert res.status_code == 200
    assert res.json() == ["source", "sink"]
    assert len(audit) >= 1
    ok, _ = audit.tamper_check()
    assert ok


def test_secret_unset_503(unsealed):
    res = unsealed.get("/api/v1/forge/kinds")
    assert res.status_code == 503
    assert res.json()["error"] == "seal_unavailable"


def test_unwritten_route_404_sealed(sealed):
    client, _ = sealed
    res = client.get("/api/nowhere", headers=_hdr())
    assert res.status_code == 404
    assert res.json()["error"] == "unwritten_route"


def test_body_bound_413(sealed):
    client, _ = sealed
    res = client.post(
        "/api/v1/forge/blueprint",
        content=b"x" * 200,
        headers={**_hdr(), "content-type": "application/octet-stream"},
    )
    assert res.status_code == 413
    assert res.json()["error"] == "scroll_too_large"


def test_worm_audit_fail_503(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)

    class Boom(AuditLog):
        def append(self, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("disk full")

        def verify_chain_or_refuse(self) -> None:
            raise RuntimeError("no")

    with TestClient(_app(audit=Boom())) as c:
        res = c.get("/api/v1/forge/kinds", headers=_hdr())
        assert res.status_code == 503
        assert res.json()["error"] == "audit_unavailable"
