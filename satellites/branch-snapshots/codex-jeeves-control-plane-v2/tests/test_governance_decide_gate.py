"""Governance decide-gate — charter law on forge mutate + swarm submit."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api.errors import map_error  # noqa: E402
from skeleton.api.hmac_seal import mint_seal  # noqa: E402
from skeleton.api.routes import router  # noqa: E402
from skeleton.api.server import get_state  # noqa: E402
from skeleton.forge.universal import Forge  # noqa: E402
from skeleton.kernel.errors import SkeletonError  # noqa: E402
from skeleton.kernel.governance import (  # noqa: E402
    Governance,
    Rule,
    get_governance,
    reset_governance,
)

SECRET = "governance-decide-gate-secret"


def _make_app() -> FastAPI:
    state = get_state()
    state.forge = Forge()
    if hasattr(state, "swarm_dag"):
        state.swarm_dag = None
    app = FastAPI()

    async def _skel_err(_request, exc: SkeletonError):
        return map_error(exc).response()

    app.add_exception_handler(SkeletonError, _skel_err)
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture(autouse=True)
def _fresh_founding_law():
    """Each test gets founding forge/swarm charters (fail-closed still covered)."""
    reset_governance()
    get_governance(bootstrap=True)
    yield
    reset_governance()


@pytest.fixture()
def sealed_client(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    with TestClient(_make_app()) as c:
        yield c


def _seal(attester: str = "gov-attester") -> dict:
    tok = mint_seal(attester, secret=SECRET)
    assert tok is not None
    return {"x-gf-seal": tok}


def test_decide_fail_closed_unchartered_domain():
    gov = Governance()
    d = gov.decide("lawless", "anything", 99)
    assert d.permitted is False
    assert d.cited_rule is None
    assert "no charter ratified" in d.reason


def test_decide_permits_written_action():
    gov = Governance()
    gov.ratify(
        "forge",
        [Rule(id="forge.blueprint", action="blueprint", min_weight=0)],
    )
    d = gov.decide("forge", "blueprint", 0)
    assert d.permitted is True
    assert d.cited_rule == "forge.blueprint"


def test_decide_denies_insufficient_weight():
    gov = Governance()
    gov.ratify(
        "forge",
        [Rule(id="forge.materialise", action="materialise", min_weight=5)],
    )
    d = gov.decide("forge", "materialise", 1)
    assert d.permitted is False
    assert d.cited_rule == "forge.materialise"
    assert "below required" in d.reason


def test_propose_and_enforce_edict():
    gov = Governance()
    gov.ratify("swarm", [Rule(id="swarm.submit", action="submit", min_weight=0)])
    proposal = gov.propose_edict(
        "swarm",
        Rule(id="swarm.cancel", action="cancel", min_weight=2),
        proposed_by="court",
    )
    assert proposal and proposal.startswith("edict:")
    edict_id = proposal.split(":", 1)[1]
    assert gov.enforce_edict(edict_id) is True
    d = gov.decide("swarm", "cancel", 2)
    assert d.permitted is True
    assert d.cited_rule == "swarm.cancel"


def test_propose_edict_missing_charter_returns_none():
    gov = Governance()
    assert gov.propose_edict("missing", Rule(id="r", action="a"), "x") is None


def test_forge_mutate_seal_then_charter_ok(sealed_client):
    res = sealed_client.post(
        "/api/v1/forge/blueprint",
        json={"name": "pipe", "components": [], "wires": []},
        headers=_seal(),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "created"


def test_forge_mutate_without_seal_still_401(sealed_client):
    res = sealed_client.post("/api/v1/forge/blueprint", json={"name": "x"})
    assert res.status_code == 401


def test_forge_mutate_unchartered_domain_403(sealed_client, monkeypatch):
    """Fail-closed: wipe charters so forge has no law → 403 after seal."""
    empty = Governance()
    monkeypatch.setattr(
        "skeleton.api.charter_gate.get_governance",
        lambda **_kw: empty,
    )
    res = sealed_client.post(
        "/api/v1/forge/blueprint",
        json={"name": "x"},
        headers=_seal(),
    )
    assert res.status_code == 403
    body = res.json()
    detail = body.get("detail", body)
    assert detail.get("error") == "charter_denied"
    assert "no charter ratified" in detail.get("reason", "")


def test_swarm_submit_seal_then_charter_ok(sealed_client):
    res = sealed_client.post(
        "/api/v1/swarm/submit",
        json={"id": "t1", "capability": "npc", "payload": {"x": 1}, "deps": []},
        headers=_seal("swarm-bot"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] is True
    assert body["task_id"] == "t1"
    assert body["attester"] == "swarm-bot"


def test_swarm_submit_unchartered_403(sealed_client, monkeypatch):
    empty = Governance()
    monkeypatch.setattr(
        "skeleton.api.charter_gate.get_governance",
        lambda **_kw: empty,
    )
    res = sealed_client.post(
        "/api/v1/swarm/submit",
        json={"id": "t2", "capability": "npc", "payload": {}, "deps": []},
        headers=_seal(),
    )
    assert res.status_code == 403
    detail = res.json().get("detail", res.json())
    assert detail.get("error") == "charter_denied"


def test_swarm_submit_without_seal_401(sealed_client):
    res = sealed_client.post(
        "/api/v1/swarm/submit",
        json={"id": "t3", "capability": "npc", "payload": {}, "deps": []},
    )
    assert res.status_code == 401


def test_actor_weight_below_charter_403(sealed_client, monkeypatch):
    gov = Governance()
    gov.ratify(
        "forge",
        [Rule(id="forge.blueprint", action="blueprint", min_weight=10)],
    )
    gov.ratify("swarm", [Rule(id="swarm.submit", action="submit", min_weight=0)])
    monkeypatch.setattr(
        "skeleton.api.charter_gate.get_governance",
        lambda **_kw: gov,
    )
    res = sealed_client.post(
        "/api/v1/forge/blueprint",
        json={"name": "x"},
        headers={**_seal(), "x-gf-actor-weight": "1"},
    )
    assert res.status_code == 403
    detail = res.json().get("detail", res.json())
    assert detail.get("error") == "charter_denied"
    assert "below required" in detail.get("reason", "")
