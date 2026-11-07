"""B031 phase 2: fallback chains, per-call budgets and capsec gating for the
router contract (``gate_receipt`` / ``execute_receipt_chain``) plus fuller
frontier-adapter budget coverage."""

from __future__ import annotations

import asyncio

import pytest

from skeleton.frontier.runtime.model_router_contract import (
    CallBudget,
    ChainCall,
    FrontierModelRouterAdapter,
    ProviderOutcome,
    RouteStatus,
    RouteTask,
    RoutingReceipt,
    execute_receipt_chain,
    gate_receipt,
)
from skeleton.frontier.runtime.model_routing import (
    ModelRouter as FrontierModelRouter,
    ModelRouteRequest,
    ProviderMetadata,
)
from skeleton.frontier.runtime.model_runtime import (
    ChatResponse,
    ModelCapability,
    ModelMessage,
    ProviderError,
    TokenUsage,
)
from skeleton.kernel.capabilities import Capability, TokenIssuer
from skeleton.kernel.capsec import DenyAllGate, InMemoryAuditSink


def _planned(chain=("a", "b", "c"), budget: CallBudget | None = None, **kw) -> RoutingReceipt:
    budget = budget or CallBudget(max_attempts=max(len(chain), 1))
    return RoutingReceipt(
        request_id="req", task_type="chat", backend="test", status=RouteStatus.PLANNED,
        selected_provider_id=chain[0] if chain else None, fallback_chain=tuple(chain[1:]),
        rejected=kw.pop("rejected", {}), budget=budget, decided_at=1.0, **kw,
    )


def _gate(*caps: Capability):
    issuer = TokenIssuer(secret=b"g" * 32)
    sink = InMemoryAuditSink()
    token = issuer.mint("bork", list(caps)) if caps else None
    return issuer.gate(sink), token, sink


ALL = Capability("*", "call")


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class Script:
    """invoke() stub: per-provider behaviours, records the call order."""

    def __init__(self, clock: FakeClock | None = None, **behaviour) -> None:
        self.behaviour = behaviour
        self.calls: list[str] = []
        self.clock = clock

    def __call__(self, provider_id: str):
        self.calls.append(provider_id)
        b = self.behaviour.get(provider_id, ProviderOutcome(value=provider_id))
        if isinstance(b, tuple) and b and b[0] == "sleep":
            if self.clock:
                self.clock.t += b[1]
            b = b[2]
        if isinstance(b, BaseException):
            raise b
        return b


def run(coro):
    return asyncio.run(coro)


# --- gate_receipt ----------------------------------------------------------

def test_gate_receipt_keeps_order_and_records_denials():
    gate, token, sink = _gate(Capability("provider.a", "call"), Capability("provider.c", "call"))
    out = gate_receipt(_planned(), gate=gate, cap=token)
    assert out.status == RouteStatus.PLANNED
    assert out.provider_chain == ("a", "c")
    assert out.rejected["b"] == ("capsec:not_covered",)
    assert out.capability_decisions == tuple(r.record_id for r in sink.records)
    assert len(sink.records) == 3


def test_gate_receipt_denies_everything_without_token():
    gate, _, sink = _gate()
    out = gate_receipt(_planned(), gate=gate, cap=None)
    assert out.status == RouteStatus.DENIED and out.provider_chain == ()
    assert set(out.rejected) == {"a", "b", "c"}
    assert all(r == ("capsec:unsigned_token",) for r in out.rejected.values())


def test_gate_receipt_appends_to_existing_rejections_and_decisions():
    gate, token, _ = _gate(Capability("provider.b", "call"))
    receipt = _planned(rejected={"a": ("slow",)}, capability_decisions=("prior",))
    out = gate_receipt(receipt, gate=gate, cap=token)
    assert out.rejected["a"] == ("slow", "capsec:not_covered")
    assert out.capability_decisions[0] == "prior" and len(out.capability_decisions) == 4


def test_gate_receipt_ignores_empty_chain():
    receipt = _planned(chain=())
    assert gate_receipt(receipt, gate=DenyAllGate(), cap="x") is receipt


# --- fallback chains -------------------------------------------------------

def test_first_success_is_served_without_touching_fallbacks():
    gate, token, _ = _gate(ALL)
    script = Script()
    call = run(execute_receipt_chain(_planned(), script, gate=gate, cap=token))
    assert isinstance(call, ChainCall) and call.ok and call.value == "a"
    assert script.calls == ["a"] and call.receipt.served_by == "a"
    assert [a.outcome for a in call.receipt.attempts] == ["ok"]


def test_falls_back_through_errors_in_chain_order():
    gate, token, _ = _gate(ALL)
    script = Script(a=ProviderError("down"), b=RuntimeError("boom"))
    call = run(execute_receipt_chain(_planned(), script, gate=gate, cap=token))
    assert call.ok and call.receipt.served_by == "c" and call.value == "c"
    assert script.calls == ["a", "b", "c"]
    assert [(a.provider_id, a.outcome, a.error_type) for a in call.receipt.attempts] == [
        ("a", "error", "ProviderError"), ("b", "error", "RuntimeError"), ("c", "ok", None),
    ]
    assert call.receipt.selected_provider_id == "a"


def test_not_ok_outcome_falls_back_and_still_spends():
    gate, token, _ = _gate(ALL)
    script = Script(a=ProviderOutcome(cost=0.1, output_tokens=7, ok=False, error_type="Refusal"),
                    b=ProviderOutcome(value="B", cost=0.2, output_tokens=3))
    call = run(execute_receipt_chain(_planned(), script, gate=gate, cap=token))
    assert call.ok and call.value == "B"
    assert call.receipt.attempts[0].error_type == "Refusal"
    assert call.receipt.spent_cost == pytest.approx(0.3)
    assert call.receipt.spent_output_tokens == 10


def test_all_providers_fail():
    gate, token, _ = _gate(ALL)
    script = Script(a=ProviderError("x"), b=ProviderError("y"), c=ProviderError("z"))
    call = run(execute_receipt_chain(_planned(), script, gate=gate, cap=token))
    assert call.receipt.status == RouteStatus.FAILED and call.value is None
    assert call.receipt.served_by is None and len(call.receipt.attempts) == 3


def test_capsec_denied_providers_are_never_invoked():
    gate, token, _ = _gate(Capability("provider.c", "call"))
    script = Script(c=ProviderOutcome(value="only-c"))
    call = run(execute_receipt_chain(_planned(), script, gate=gate, cap=token))
    assert script.calls == ["c"] and call.value == "only-c"
    assert call.receipt.rejected["a"] == ("capsec:not_covered",)


def test_fully_denied_chain_makes_no_call():
    script = Script()
    call = run(execute_receipt_chain(_planned(), script, gate=DenyAllGate(), cap="t"))
    assert call.receipt.status == RouteStatus.DENIED and script.calls == []


def test_non_planned_receipt_is_returned_unchanged():
    gate, token, _ = _gate(ALL)
    receipt = RoutingReceipt(request_id="r", task_type="t", backend="b", status=RouteStatus.NO_ROUTE,
                             selected_provider_id=None, fallback_chain=(), rejected={},
                             budget=CallBudget(), decided_at=0.0)
    script = Script()
    call = run(execute_receipt_chain(receipt, script, gate=gate, cap=token))
    assert call.receipt is receipt and script.calls == []


def test_async_invoke_and_plain_return_values():
    gate, token, _ = _gate(ALL)

    async def invoke(pid):
        if pid == "a":
            raise ProviderError("down")
        return {"text": pid}

    call = run(execute_receipt_chain(_planned(), invoke, gate=gate, cap=token))
    assert call.ok and call.value == {"text": "b"}


def test_cancellation_propagates():
    gate, token, _ = _gate(ALL)

    async def invoke(pid):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        run(execute_receipt_chain(_planned(), invoke, gate=gate, cap=token))


# --- per-call budgets ------------------------------------------------------

def test_max_attempts_bounds_the_chain():
    with pytest.raises(ValueError):
        _planned(chain=("a", "b", "c"), budget=CallBudget(max_attempts=2))
    gate, token, _ = _gate(ALL)
    script = Script(a=ProviderError("x"), b=ProviderError("y"))
    call = run(execute_receipt_chain(_planned(("a", "b"), CallBudget(max_attempts=2)),
                                     script, gate=gate, cap=token))
    assert script.calls == ["a", "b"] and call.receipt.status == RouteStatus.FAILED


def test_cost_budget_overrun_is_not_served():
    gate, token, _ = _gate(ALL)
    script = Script(a=ProviderOutcome(value="pricey", cost=2.0))
    call = run(execute_receipt_chain(_planned(budget=CallBudget(max_cost=1.0)), script,
                                     gate=gate, cap=token))
    r = call.receipt
    assert r.status == RouteStatus.BUDGET_EXHAUSTED and call.value is None and r.served_by is None
    assert r.attempts[0].outcome == "budget_exhausted" and r.spent_cost == 2.0
    assert r.rejected["a"] == ("cost budget exceeded",)
    assert r.rejected["b"] == ("not attempted: cost budget exceeded",)
    assert script.calls == ["a"]


def test_cost_budget_spent_on_failures_blocks_further_fallback():
    gate, token, _ = _gate(ALL)
    script = Script(a=ProviderOutcome(cost=1.0, ok=False))
    call = run(execute_receipt_chain(_planned(budget=CallBudget(max_cost=1.0)), script,
                                     gate=gate, cap=token))
    assert call.receipt.status == RouteStatus.BUDGET_EXHAUSTED
    assert script.calls == ["a"]
    assert call.receipt.rejected["b"] == ("not attempted: cost budget exhausted",)


def test_zero_cost_budget_allows_free_providers():
    gate, token, _ = _gate(ALL)
    call = run(execute_receipt_chain(_planned(budget=CallBudget(max_cost=0.0)), Script(),
                                     gate=gate, cap=token))
    assert call.ok and call.receipt.spent_cost == 0.0


def test_output_token_budget():
    gate, token, _ = _gate(ALL)
    over = Script(a=ProviderOutcome(value="long", output_tokens=101))
    call = run(execute_receipt_chain(_planned(budget=CallBudget(max_output_tokens=100)), over,
                                     gate=gate, cap=token))
    assert call.receipt.status == RouteStatus.BUDGET_EXHAUSTED
    assert call.receipt.rejected["a"] == ("output token budget exceeded",)
    exact = Script(a=ProviderOutcome(value="fits", output_tokens=100))
    ok = run(execute_receipt_chain(_planned(budget=CallBudget(max_output_tokens=100)), exact,
                                   gate=gate, cap=token))
    assert ok.ok and ok.receipt.spent_output_tokens == 100


def test_output_tokens_spent_on_failure_exhaust_budget():
    gate, token, _ = _gate(ALL)
    script = Script(a=ProviderOutcome(output_tokens=50, ok=False))
    call = run(execute_receipt_chain(_planned(budget=CallBudget(max_output_tokens=50)), script,
                                     gate=gate, cap=token))
    assert call.receipt.status == RouteStatus.BUDGET_EXHAUSTED and script.calls == ["a"]


def test_latency_budget_with_fake_clock_skips_remaining_chain():
    gate, token, _ = _gate(ALL)
    clock = FakeClock()
    script = Script(clock, a=("sleep", 0.2, ProviderError("slow fail")))
    call = run(execute_receipt_chain(_planned(budget=CallBudget(max_latency_ms=150)), script,
                                     gate=gate, cap=token, clock=clock))
    r = call.receipt
    assert r.status == RouteStatus.BUDGET_EXHAUSTED and script.calls == ["a"]
    assert r.attempts[0].latency_ms == pytest.approx(200.0)
    assert r.rejected["b"] == ("not attempted: latency budget exhausted",)


def test_late_success_beyond_latency_budget_is_not_served():
    gate, token, _ = _gate(ALL)
    clock = FakeClock()
    script = Script(clock, a=("sleep", 0.3, ProviderOutcome(value="late")))
    call = run(execute_receipt_chain(_planned(budget=CallBudget(max_latency_ms=100)), script,
                                     gate=gate, cap=token, clock=clock))
    assert call.receipt.status == RouteStatus.BUDGET_EXHAUSTED and call.value is None
    assert call.receipt.rejected["a"] == ("latency budget exceeded",)


def test_async_provider_is_cut_off_at_remaining_latency():
    gate, token, _ = _gate(ALL)

    async def invoke(pid):
        await asyncio.sleep(5)
        return pid

    call = run(execute_receipt_chain(_planned(budget=CallBudget(max_latency_ms=30)), invoke,
                                     gate=gate, cap=token))
    r = call.receipt
    assert r.attempts[0].outcome == "timeout" and r.attempts[0].latency_ms < 2_000
    assert r.status == RouteStatus.BUDGET_EXHAUSTED
    assert r.rejected["b"] == ("not attempted: latency budget exhausted",)


def test_receipt_digest_reflects_execution():
    gate, token, _ = _gate(ALL)
    planned = _planned()
    call = run(execute_receipt_chain(planned, Script(), gate=gate, cap=token))
    assert call.receipt.receipt_digest() != planned.receipt_digest()
    assert call.receipt.as_dict()["served_by"] == "a"


@pytest.mark.parametrize("kwargs", [{"cost": -1}, {"output_tokens": -1}, {"cost": float("inf")}])
def test_provider_outcome_validation(kwargs):
    with pytest.raises(ValueError):
        ProviderOutcome(**kwargs)


# --- frontier adapter: budgets end to end ----------------------------------

class FakeAdapter:
    def __init__(self, name: str, *, fail: bool = False, out_tokens: int = 5) -> None:
        self.name = name
        self.capabilities = frozenset({ModelCapability.CHAT})
        self.fail = fail
        self.out_tokens = out_tokens
        self.calls = 0

    async def chat(self, request):
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name} down")
        return ChatResponse(model=self.name, text="hi", usage=TokenUsage(10, self.out_tokens))

    def stream_chat(self, request):  # pragma: no cover - unused
        raise NotImplementedError

    async def embed(self, request):  # pragma: no cover - unused
        raise NotImplementedError


def _frontier(fails=(), cost=1.0):
    router = FrontierModelRouter()
    adapters = {p: FakeAdapter(p, fail=p in fails) for p in ("alpha", "beta", "gamma")}
    for i, (pid, adapter) in enumerate(adapters.items()):
        router.register(ProviderMetadata(
            provider_id=pid, adapter_name=pid, model=f"{pid}-m",
            capabilities=frozenset({"chat"}), max_input_tokens=10_000,
            max_output_tokens=1_000, input_cost_per_million=cost,
            output_cost_per_million=cost, timeout_seconds=2.0, priority=i,
            max_attempts=1,
        ), adapter)
    return FrontierModelRouterAdapter(router, clock=lambda: 7.0), adapters


def _req() -> ModelRouteRequest:
    return ModelRouteRequest(request_id="fr", messages=(ModelMessage(role="user", content="hi"),),
                             required_capabilities=frozenset({"chat"}), max_output_tokens=50)


def test_frontier_execute_respects_max_attempts():
    adapter, adapters = _frontier(fails=("alpha", "beta"))
    gate, token, _ = _gate(ALL)
    call = run(adapter.execute(_req(), gate=gate, cap=token, budget=CallBudget(max_attempts=2)))
    assert not call.ok
    assert adapters["gamma"].calls == 0
    assert len(call.receipt.provider_chain) <= 2


def test_frontier_execute_falls_back_to_last_provider():
    adapter, adapters = _frontier(fails=("alpha", "beta"))
    gate, token, _ = _gate(ALL)
    call = run(adapter.execute(_req(), gate=gate, cap=token, budget=CallBudget(max_attempts=3)))
    assert call.ok and call.receipt.served_by == "gamma"
    assert [a.outcome for a in call.receipt.attempts] == ["error", "error", "ok"]


def test_frontier_select_then_execute_receipt_chain_interops():
    adapter, _ = _frontier()
    gate, token, _ = _gate(Capability("provider.beta", "call"))
    receipt = adapter.select(RouteTask("chat"), CallBudget(max_attempts=3))
    call = run(execute_receipt_chain(receipt, lambda pid: ProviderOutcome(value=pid),
                                     gate=gate, cap=token))
    assert call.ok and call.value == "beta"
    assert call.receipt.backend == "frontier"
