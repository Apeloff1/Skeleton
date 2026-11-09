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


def test_provider_capability_grants_reject_wildcards_and_unbounded_iterators():
    from itertools import repeat

    _, issuer = gate_and_issuer()
    for providers in (["*"], ["../other"], ["bad:scope"], [""], repeat("alpha")):
        with pytest.raises(ValueError):
            grant_providers(issuer, providers)


def test_planner_output_and_request_identity_budgets_fail_closed():
    gate, issuer = gate_and_issuer()
    cap = grant_providers(issuer, ["alpha"])
    for invalid in (0, -1, 4097, True):
        with pytest.raises(ValueError, match="token budget"):
            ModelPlanner(FakeRouter(), gate=gate, cap=cap, max_output_tokens=invalid)
    for rid in ("", "x" * 129, "../escape", "req\nforged"):
        with pytest.raises(ValueError, match="request identity"):
            run(ModelPlanner(FakeRouter(), gate=gate, cap=cap).plan(BRIEF, request_id=rid))


def test_prompt_normalizer_bounds_before_unicode_expansion_and_router():
    from skeleton.forge.ai_builder.prompt_normalizer import MAX_RAW_PROMPT_CHARS, normalize_prompt
    from skeleton.forge.game_design_spec import BRIEF_MAX

    assert normalize_prompt("  hello\\tworld  ", limit=8) == "hello wo"
    for invalid in (0, -1, True, 1.5, BRIEF_MAX + 1):
        with pytest.raises(ValueError, match="output limit"):
            normalize_prompt("hello", limit=invalid)
    with pytest.raises(ValueError, match="input budget"):
        normalize_prompt("x" * (MAX_RAW_PROMPT_CHARS + 1))
    # NFKC may expand compatibility characters, so the post-normalization
    # budget must also hold before whitespace cleanup and model routing.
    with pytest.raises(ValueError, match="normalized prompt"):
        normalize_prompt("\ufb03" * (MAX_RAW_PROMPT_CHARS // 2))

    gate, issuer = gate_and_issuer()
    router = FakeRouter()
    with pytest.raises(ValueError, match="input budget"):
        run(ModelPlanner(router, gate=gate, cap=grant_providers(issuer, ["alpha"]))
            .plan("x" * (MAX_RAW_PROMPT_CHARS + 1)))
    assert router.invoked == []


def test_provider_grant_rejects_scalar_string_and_unbounded_subject():
    _, issuer = gate_and_issuer()
    for providers in ("alpha", b"alpha", bytearray(b"alpha")):
        with pytest.raises(ValueError, match="bounded iterable"):
            grant_providers(issuer, providers)
    for subject in ("", "../admin", "forge\\nforged", "x" * 129, None):
        with pytest.raises(ValueError, match="subject"):
            grant_providers(issuer, ["alpha"], subject=subject)


def test_malformed_structured_provider_result_falls_back_without_leaking():
    from types import SimpleNamespace
    from skeleton.frontier.runtime.model_router_contract import RoutedCall

    class PoisonResponse:
        @property
        def structured(self):
            raise RuntimeError("private provider payload must not leak")

    class HostileRouter(FakeRouter):
        async def execute(self, *args, **kwargs):
            original = await super().execute(*args, **kwargs)
            return RoutedCall(original.receipt, SimpleNamespace(response=PoisonResponse()))

    gate, issuer = gate_and_issuer()
    out = run(ModelPlanner(
        HostileRouter(), gate=gate, cap=grant_providers(issuer, ["alpha"]),
    ).plan(BRIEF))
    assert out.source == "compiler"
    assert out.fallback_reason == "parse:RuntimeError"
    assert "private" not in out.fallback_reason
    assert out.spec == out.compiled


def test_oversized_structured_provider_shape_falls_back_before_copy():
    from types import SimpleNamespace
    from skeleton.frontier.runtime.model_router_contract import RoutedCall

    class OversizedRouter(FakeRouter):
        async def execute(self, *args, **kwargs):
            original = await super().execute(*args, **kwargs)
            response = SimpleNamespace(structured={str(i): i for i in range(65)})
            return RoutedCall(original.receipt, SimpleNamespace(response=response))

    gate, issuer = gate_and_issuer()
    out = run(ModelPlanner(
        OversizedRouter(), gate=gate, cap=grant_providers(issuer, ["alpha"]),
    ).plan(BRIEF))
    assert out.source == "compiler"
    assert out.fallback_reason == "parse:PlanParseError"
