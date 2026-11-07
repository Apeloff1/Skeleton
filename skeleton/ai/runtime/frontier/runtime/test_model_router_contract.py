"""Contract tests for the B031 unified ModelRouter interface (phase 1)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from skeleton.frontier.runtime.model_router_contract import (
    ROUTER_INTERFACE_VERSION,
    CallBudget,
    ExecutingModelRouter,
    FrontierModelRouterAdapter,
    ModelRouter,
    RouteStatus,
    RouteTask,
    RoutingReceipt,
    RoutingReceiptMismatch,
    link_context_receipt,
    provider_action,
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
from skeleton.kernel.capsec import InMemoryAuditSink, KernelCapabilityGate


class FakeAdapter:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self.capabilities = frozenset({ModelCapability.CHAT})
        self.fail = fail
        self.calls = 0

    async def chat(self, request):
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name} down")
        return ChatResponse(model=self.name, text="hi", usage=TokenUsage(10, 5))

    def stream_chat(self, request):  # pragma: no cover - unused
        raise NotImplementedError

    async def embed(self, request):  # pragma: no cover - unused
        raise NotImplementedError


def _meta(pid: str, priority: int, cost: float = 1.0) -> ProviderMetadata:
    return ProviderMetadata(
        provider_id=pid, adapter_name=pid, model=f"{pid}-m",
        capabilities=frozenset({"chat"}), max_input_tokens=10_000,
        max_output_tokens=1_000, input_cost_per_million=cost,
        output_cost_per_million=cost, timeout_seconds=2.0, priority=priority,
        max_attempts=1,
    )


def _router(fail_primary: bool = False):
    router = FrontierModelRouter()
    adapters = {
        "alpha": FakeAdapter("alpha", fail=fail_primary),
        "beta": FakeAdapter("beta"),
        "gamma": FakeAdapter("gamma"),
    }
    for i, (pid, adapter) in enumerate(adapters.items()):
        router.register(_meta(pid, i), adapter)
    return FrontierModelRouterAdapter(router, clock=lambda: 123.0), adapters


def _request(rid: str = "r1") -> ModelRouteRequest:
    return ModelRouteRequest(
        request_id=rid,
        messages=(ModelMessage(role="user", content="hello"),),
        required_capabilities=frozenset({"chat"}),
        max_output_tokens=50,
    )


def _gate(*caps: Capability):
    issuer = TokenIssuer(secret=b"k" * 32)
    sink = InMemoryAuditSink()
    token = issuer.mint("bork", list(caps)) if caps else None
    return KernelCapabilityGate(issuer, sink), token, sink


def test_protocol_conformance_and_version():
    adapter, _ = _router()
    assert ROUTER_INTERFACE_VERSION == 1
    assert isinstance(adapter, ModelRouter)
    assert isinstance(adapter, ExecutingModelRouter)


def test_select_returns_ordered_chain_bounded_by_budget():
    adapter, adapters = _router()
    receipt = adapter.select(RouteTask("chat"), CallBudget(max_attempts=2))
    assert isinstance(receipt, RoutingReceipt)
    assert receipt.status == RouteStatus.PLANNED
    assert receipt.provider_chain == ("alpha", "beta")
    assert receipt.served_by is None
    assert all(a.calls == 0 for a in adapters.values())  # select never calls


def test_select_honours_exclusions_and_preferences():
    adapter, _ = _router()
    task = RouteTask("chat", excluded_providers=frozenset({"alpha"}),
                     preferred_providers=("gamma",))
    receipt = adapter.select(task, CallBudget(max_attempts=3))
    assert receipt.provider_chain == ("gamma", "beta")
    assert receipt.rejected["alpha"] == ("excluded by task",)


def test_select_budget_exhaustion_and_no_route():
    adapter, _ = _router()
    tight = adapter.select(RouteTask("chat", estimated_input_tokens=5_000),
                           CallBudget(max_cost=0.0000001))
    assert tight.status == RouteStatus.BUDGET_EXHAUSTED and tight.selected_provider_id is None
    none = adapter.select(RouteTask("embed", required_capabilities=frozenset({"embeddings"})))
    assert none.status == RouteStatus.NO_ROUTE


def test_receipt_digest_is_stable_and_ignores_wall_clock():
    adapter, _ = _router()
    a = adapter.select(RouteTask("chat", request_id="x"))
    b = RoutingReceipt(**{**{f: getattr(a, f) for f in a.__slots__}, "decided_at": 999.0})
    assert a.receipt_digest() == b.receipt_digest()
    assert a.as_dict()["receipt_digest"] == a.receipt_digest()


def test_execute_falls_back_and_records_served_by():
    adapter, adapters = _router(fail_primary=True)
    gate, token, sink = _gate(Capability("*", "call"))
    call = asyncio.run(adapter.execute(_request(), gate=gate, cap=token))
    assert call.ok
    assert call.receipt.selected_provider_id == "alpha"
    assert call.receipt.served_by == "beta"
    assert [a.provider_id for a in call.receipt.attempts][:2] == ["alpha", "beta"]
    assert len(call.receipt.capability_decisions) == 3 == len(sink.records)


def test_execute_is_deny_by_default_without_token():
    adapter, adapters = _router()
    gate, _, sink = _gate()
    call = asyncio.run(adapter.execute(_request(), gate=gate, cap=None))
    assert call.receipt.status == RouteStatus.DENIED and call.result is None
    assert all(a.calls == 0 for a in adapters.values())
    assert all(r.startswith("capsec:") for rs in call.receipt.rejected.values() for r in rs)
    assert len(sink.records) == 3


def test_execute_skips_providers_capsec_denies():
    adapter, adapters = _router()
    gate, token, _ = _gate(Capability("provider.gamma", "call"))
    call = asyncio.run(adapter.execute(_request(), gate=gate, cap=token))
    assert call.ok and call.receipt.served_by == "gamma"
    assert adapters["alpha"].calls == 0 and adapters["beta"].calls == 0
    assert call.receipt.rejected["alpha"] == ("capsec:not_covered",)


def test_provider_action_shape():
    action = provider_action("openai")
    assert (action.scope, action.verb, action.resource) == ("provider.openai", "call", "openai")


@dataclass
class _Ctx:
    request_id: str
    selected_provider_id: str | None
    fallback_provider_ids: tuple[str, ...]

    def receipt_digest(self) -> str:
        return "sha256:abc"


def test_link_context_receipt_binds_and_fails_closed():
    adapter, _ = _router(fail_primary=True)
    gate, token, _ = _gate(Capability("*", "call"))
    receipt = asyncio.run(adapter.execute(_request(), gate=gate, cap=token)).receipt
    linked = link_context_receipt(receipt, _Ctx("r1", "beta", receipt.fallback_chain))
    assert linked.context_receipt_digest == "sha256:abc"
    assert linked.receipt_digest() != receipt.receipt_digest()
    with pytest.raises(RoutingReceiptMismatch):
        link_context_receipt(receipt, _Ctx("r1", "alpha", receipt.fallback_chain))
    with pytest.raises(RoutingReceiptMismatch):
        link_context_receipt(receipt, _Ctx("other", "beta", receipt.fallback_chain))


@pytest.mark.parametrize("kwargs", [
    {"max_attempts": 0}, {"max_cost": -1}, {"max_latency_ms": float("nan")},
    {"max_output_tokens": -3},
])
def test_call_budget_validation(kwargs):
    with pytest.raises(ValueError):
        CallBudget(**kwargs)


def test_receipt_invariants():
    with pytest.raises(ValueError):
        RoutingReceipt(request_id="r", task_type="t", backend="b", status="ok",
                       selected_provider_id="a", fallback_chain=(), rejected={},
                       budget=CallBudget(), decided_at=0.0)  # ok without served_by
    with pytest.raises(ValueError):
        RoutingReceipt(request_id="r", task_type="t", backend="b", status="planned",
                       selected_provider_id="a", fallback_chain=("b", "c", "d"),
                       rejected={}, budget=CallBudget(max_attempts=3), decided_at=0.0)
