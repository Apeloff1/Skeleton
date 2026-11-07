import asyncio

import pytest

from skeleton.forge.ai_builder import ModelPlanner, grant_providers
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS, compile_brief
from skeleton.frontier.runtime.model_router_contract import RouteStatus

from .fakes import FakeRouter, gate_and_issuer

BRIEF = GOLDEN_BRIEFS[1]["brief"]


def run(c):
    return asyncio.run(c)


def test_granted_provider_refines_plan():
    gate, issuer = gate_and_issuer()
    router = FakeRouter()
    out = run(ModelPlanner(router, gate=gate, cap=grant_providers(issuer, ["alpha"])).plan(BRIEF))
    assert out.source == "model" and out.receipt.status == RouteStatus.OK
    assert out.receipt.served_by == "alpha" and router.invoked == ["alpha"]
    assert out.spec["title"] == "Ledge Runner"
    for k in ("genre", "engine", "brief", "scope"):
        assert out.spec[k] == out.compiled[k]
    assert out.spec["spec_id"] != out.compiled["spec_id"]
    assert len(out.receipt.capability_decisions) >= 1


def test_denied_provider_falls_back_to_compile_brief_with_receipt():
    gate, issuer = gate_and_issuer()
    router = FakeRouter(chain=("alpha",))
    cap = grant_providers(issuer, ["other"])  # alpha not covered
    out = run(ModelPlanner(router, gate=gate, cap=cap).plan(BRIEF))
    assert out.source == "compiler" and router.invoked == []
    assert out.spec == compile_brief(BRIEF)
    assert out.receipt.status == RouteStatus.DENIED
    assert any(r.startswith("capsec:") for rs in out.receipt.rejected.values() for r in rs)
    assert out.fallback_reason == "route:denied"


def test_no_token_is_denied_by_default():
    gate, _ = gate_and_issuer()
    router = FakeRouter(chain=("alpha",))
    out = run(ModelPlanner(router, gate=gate, cap=None).plan(BRIEF))
    assert out.source == "compiler" and router.invoked == []
    assert out.receipt.status == RouteStatus.DENIED


def test_partial_grant_skips_denied_primary():
    gate, issuer = gate_and_issuer()
    router = FakeRouter(chain=("alpha", "beta"))
    out = run(ModelPlanner(router, gate=gate, cap=grant_providers(issuer, ["beta"])).plan(BRIEF))
    assert router.invoked == ["beta"] and out.receipt.served_by == "beta"
    assert "alpha" in out.receipt.rejected


def test_bad_output_falls_back():
    gate, issuer = gate_and_issuer()
    router = FakeRouter(chain=("alpha",), reply=lambda pid: "not json")
    out = run(ModelPlanner(router, gate=gate, cap=grant_providers(issuer, ["alpha"])).plan(BRIEF))
    assert out.source == "compiler" and out.fallback_reason.startswith("parse:")
    assert out.receipt.status == RouteStatus.OK


def test_provider_failure_falls_back_with_failed_receipt():
    gate, issuer = gate_and_issuer()
    router = FakeRouter(chain=("alpha",), reply=lambda pid: RuntimeError("down"))
    out = run(ModelPlanner(router, gate=gate, cap=grant_providers(issuer, ["alpha"])).plan(BRIEF))
    assert out.source == "compiler" and out.receipt.status == RouteStatus.FAILED


def test_router_exception_still_returns_receipt():
    class Boom:
        async def execute(self, *a, **k):
            raise ConnectionError("x")

    gate, issuer = gate_and_issuer()
    out = run(ModelPlanner(Boom(), gate=gate, cap=grant_providers(issuer, ["a"])).plan(BRIEF))
    assert out.source == "compiler" and out.receipt.status == RouteStatus.FAILED
    assert out.fallback_reason == "router_error:ConnectionError"


def test_gate_required_and_grant_nonempty():
    _, issuer = gate_and_issuer()
    with pytest.raises(ValueError):
        ModelPlanner(FakeRouter(), gate=None, cap=None)
    with pytest.raises(ValueError):
        grant_providers(issuer, [])


def test_request_carries_schema_and_bounds():
    gate, issuer = gate_and_issuer()
    router = FakeRouter()
    run(ModelPlanner(router, gate=gate, cap=grant_providers(issuer, ["alpha"])).plan(BRIEF))
    req = router.requests[0]
    assert req.response_schema["properties"]["schema"]["const"].endswith("plan_proposal.v1")
    assert req.max_output_tokens == 800 and req.messages[0].role == "system"
