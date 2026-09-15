"""TestClient coverage: HMAC seal gate on forge mutate routes."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api.hmac_seal import mint_seal  # noqa: E402
from skeleton.api.routes import router  # noqa: E402
from skeleton.api.server import get_state, skeleton_error_handler  # noqa: E402
from skeleton.forge.universal import Forge  # noqa: E402
from skeleton.kernel.errors import SkeletonError  # noqa: E402

SECRET = "forge-gate-test-secret"


def _make_app() -> FastAPI:
    """Minimal app without lifespan/cortex (both broken on main tip).

    Seeds AppState.forge so mutate handlers can run after the seal Depends.
    Does not edit server.py lifespan.
    """
    state = get_state()
    state.forge = Forge()
    app = FastAPI()
    app.add_exception_handler(SkeletonError, skeleton_error_handler)
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture()
def sealed_client(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    with TestClient(_make_app()) as c:
        yield c


@pytest.fixture()
def unsealed_client(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    with TestClient(_make_app()) as c:
        yield c


def _seal(attester: str = "test-attester") -> dict:
    tok = mint_seal(attester, secret=SECRET)
    assert tok is not None
    return {"x-gf-seal": tok}


def test_mutate_without_seal_401(sealed_client):
    res = sealed_client.post("/api/v1/forge/blueprint", json={"name": "x"})
    assert res.status_code == 401


def test_mutate_with_seal_ok(sealed_client):
    res = sealed_client.post(
        "/api/v1/forge/blueprint",
        json={"name": "pipe", "components": [], "wires": []},
        headers=_seal(),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "created"


def test_materialise_with_seal_business_ok(sealed_client):
    res = sealed_client.post(
        "/api/v1/forge/materialise",
        json={
            "name": "pipe",
            "components": [
                {"kind": "source", "instance_id": "a"},
                {"kind": "sink", "instance_id": "b"},
            ],
            "wires": [{"from": ["a", "out"], "to": ["b", "in"]}],
        },
        headers=_seal("org.bot"),
    )
    # seal passed; business status 200 (or verify_loop shape from #7)
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") == "materialised" or "artefact" in body


def test_secret_unset_503(unsealed_client):
    res = unsealed_client.post("/api/v1/forge/blueprint", json={"name": "x"})
    assert res.status_code == 503


def test_get_kinds_open(sealed_client):
    res = sealed_client.get("/api/v1/forge/kinds")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_kinds_open_without_secret(unsealed_client):
    res = unsealed_client.get("/api/v1/forge/kinds")
    assert res.status_code == 200
