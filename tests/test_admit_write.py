"""admit_write + live create_app gate wire — Middleware sibling port."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api.admit_write import (  # noqa: E402
    EmergencyReadOnlyError,
    ShedError,
    admit_write,
    set_defaults,
)
from skeleton.api.hmac_seal import mint_seal  # noqa: E402
from skeleton.api.middleware import GatePolicy, install_gate  # noqa: E402
from skeleton.kernel.adaptive_gate import AdaptiveGate  # noqa: E402
from skeleton.kernel.chaos import ChaosGovernor, Rung  # noqa: E402
from skeleton.vault.audit import AuditLog  # noqa: E402

SECRET = "mw-admit-write-test-secret"


def test_admit_write_ok():
    gate = AdaptiveGate(capacity=10, refill_per_sec=10)
    gov = ChaosGovernor(min_samples=1000)
    admit_write(gate=gate, governor=gov)  # no raise


def test_admit_write_shed():
    gate = AdaptiveGate(capacity=0, refill_per_sec=0)
    gov = ChaosGovernor(min_samples=1000)
    with pytest.raises(ShedError):
        admit_write(priority=1, gate=gate, governor=gov)


def test_admit_write_emergency_read_only():
    gate = AdaptiveGate(capacity=10, refill_per_sec=10)
    gov = ChaosGovernor(escalate_at=0.0, recover_at=-1.0, min_samples=1, window_span=60.0)
    # Force emergency rung via observes
    for _ in range(8):
        gov.observe(False)
    assert gov.rung() == Rung.EMERGENCY_READ_ONLY
    with pytest.raises(EmergencyReadOnlyError):
        admit_write(gate=gate, governor=gov)


def _hdr(attester: str = "mw-bot") -> dict:
    tok = mint_seal(attester, secret=SECRET)
    assert tok
    return {"x-gf-seal": tok}


def test_write_admit_middleware_shed(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    from fastapi import FastAPI

    gate = AdaptiveGate(capacity=0, refill_per_sec=0)
    gov = ChaosGovernor(min_samples=1000)
    app = FastAPI()

    @app.post("/api/v1/forge/blueprint")
    async def blueprint():
        return {"status": "created"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    install_gate(app, policy=GatePolicy(), audit_log=AuditLog(), write_gate=gate, write_governor=gov)
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        res = c.post("/api/v1/forge/blueprint", headers=_hdr(), json={})
        assert res.status_code == 429
        assert res.json()["error"] == "shed"


def test_create_app_installs_gate(monkeypatch):
    """Live factory must seal protected routes (was test-only before)."""
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    # Avoid heavy genesis boot on first protected call path — root/health probes only.
    from skeleton.api import server as srv

    # Reset global state so startup does not run mid-test unexpectedly
    srv._state = None

    # Patch Genesis boot to no-op lightweight wire
    class _FakeGenesis:
        def __init__(self, *a, **k):
            self.handles = {}
            self.bus = None

        def boot(self):
            return self

    monkeypatch.setattr("skeleton.genesis.Genesis", _FakeGenesis)

    def _light_wire(self, genesis):
        self.genesis = genesis
        self.jeeves = None

    monkeypatch.setattr(srv.ServerState, "wire_from_genesis", _light_wire)

    app = srv.create_app()
    with TestClient(app) as c:
        assert c.get("/").status_code == 200
        assert c.get("/cortex/status").status_code in (200, 500)  # cortex live may miss bus
        # Protected forge-ish path without seal → 401
        res = c.get("/api/v1/forge/kinds")
        assert res.status_code == 401, res.text
        assert res.json().get("error") in ("invalid_seal", "seal_required")
        # Sealed request gets past the gate (route may still 500 without full genesis)
        sealed = c.get("/api/v1/forge/kinds", headers=_hdr())
        assert sealed.status_code != 401


def test_root_open_is_exact():
    p = GatePolicy(open_prefixes=("/", "/health"))
    assert p.is_open_route("/")
    assert p.is_open_route("/health")
    assert not p.is_open_route("/api/v1/forge/kinds")
