"""Performance regressions for the API request middleware hot path."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api.hmac_seal import mint_seal  # noqa: E402
from skeleton.api.middleware import install_gate  # noqa: E402
from skeleton.vault.audit import AuditLog  # noqa: E402

SECRET = "backend-hot-path-test-secret"


class _NoRequestPathFullScanAudit(AuditLog):
    """Make an accidental O(n) request-path chain scan fail immediately."""

    def verify_chain_or_refuse(self) -> None:
        raise AssertionError("full audit history must not be rescanned per request")


def test_request_audit_append_does_not_rescan_full_history(monkeypatch) -> None:
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    audit = _NoRequestPathFullScanAudit()
    app = FastAPI()

    @app.get("/api/v1/forge/kinds")
    async def kinds():
        return ["source", "sink"]

    install_gate(app, audit_log=audit)
    token = mint_seal("perf-bot", secret=SECRET)
    assert token

    with TestClient(app) as client:
        headers = {"x-gf-seal": token}
        for _ in range(8):
            response = client.get("/api/v1/forge/kinds", headers=headers)
            assert response.status_code == 200

    assert len(audit) == 8
    # Full verification remains available for boot/diagnostic integrity checks;
    # call the base implementation explicitly because the subclass blocks it
    # on the request path by design.
    AuditLog.verify_chain_or_refuse(audit)
