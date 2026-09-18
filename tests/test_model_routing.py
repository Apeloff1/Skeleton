"""Offline fake-provider coverage for the product/runtime routing contract."""

from __future__ import annotations

import asyncio
import math

import pytest

from skeleton.frontier.model_routing import (
    ModelRouter,
    ModelRouteRequest,
    ProviderMetadataError,
    RouteBudget,
    RouteEvalCase,
    RouteEvalContract,
)
from skeleton.frontier.model_runtime import (
    ChatResponse,
    ModelCapability,
    ModelMessage,
    RetryPolicy,
    TokenUsage,
    TransientProviderError,
)
from skeleton.observability.redaction import REDACTED

_SECRET = "super-secret-routing-token"


class FakeAdapter:
    def __init__(
        self,
        name: str,
        *,
        capabilities=frozenset({ModelCapability.CHAT}),
        text: str = "ok",
        usage: TokenUsage | None = None,
        fail_times: int = 0,
        error: Exception | None = None,
        delay: float = 0.0,
        calls: list | None = None,
    ) -> None:
        self.name = name
        self.capabilities = capabilities
        self.text = text
        self.usage = usage or TokenUsage(input_tokens=2, output_tokens=2)
        self.fail_times = fail_times
        self.error = error or TransientProviderError("temporary")
        self.delay = delay
        self.calls = calls if calls is not None else []

    async def chat(self, request):
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.error
        return ChatResponse(model=request.model, text=self.text, usage=self.usage)

    async def embed(self, request):
        raise AssertionError("routing tests must not call embed")

    async def stream_chat(self, request):
        if False:
            yield None
        raise AssertionError("routing tests must not call stream_chat")


def _metadata(
    provider_id: str,
    *,
    adapter_name: str | None = None,
    model: str | None = None,
    capabilities=("chat",),
    priority: int = 10,
    timeout_seconds: float = 1.0,
    input_cost: float = 1.0,
    output_cost: float = 2.0,
    max_attempts: int = 2,
    enabled: bool = True,
    max_input_tokens: int = 8_000,
    max_output_tokens: int = 1_000,
) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "adapter_name": adapter_name or provider_id,
        "model": model or f"{provider_id}-model",
        "capabilities": capabilities,
        "max_input_tokens": max_input_tokens,
        "max_output_tokens": max_output_tokens,
        "input_cost_per_million": input_cost,
        "output_cost_per_million": output_cost,
        "timeout_seconds": timeout_seconds,
        "priority": priority,
        "enabled": enabled,
        "max_attempts": max_attempts,
        "backoff_seconds": 0.0,
    }


def _request(
    request_id: str = "req-1",
    *,
    capabilities=("chat",),
    timeout_seconds: float = 1.0,
    budget: RouteBudget | None = None,
    metadata: dict | None = None,
    estimated_input_tokens: int = 10,
    max_output_tokens: int = 20,
    retry_attempts: int = 2,
) -> ModelRouteRequest:
    return ModelRouteRequest(
        request_id=request_id,
        messages=(ModelMessage("user", "hello"),),
        required_capabilities=frozenset(capabilities),
        timeout_seconds=timeout_seconds,
        retry_policy=RetryPolicy(max_attempts=retry_attempts, backoff_seconds=0.0),
        budget=budget or RouteBudget(max_cost=1.0, max_provider_attempts=3),
        estimated_input_tokens=estimated_input_tokens,
        max_output_tokens=max_output_tokens,
        metadata=metadata or {},
    )


def _router_with(*pairs: tuple[dict, FakeAdapter]) -> ModelRouter:
    router = ModelRouter()
    for metadata, adapter in pairs:
        router.register(metadata, adapter)
    return router


@pytest.mark.parametrize("max_attempts", [True, 1.5, "2"])
def test_retry_policy_rejects_non_integer_attempt_counts(max_attempts) -> None:
    with pytest.raises(TypeError, match="max_attempts"):
        RetryPolicy(max_attempts=max_attempts)


@pytest.mark.parametrize("backoff", [math.nan, math.inf, -math.inf])
def test_retry_policy_rejects_non_finite_backoff(backoff: float) -> None:
    with pytest.raises(ValueError, match="backoff_seconds"):
        RetryPolicy(backoff_seconds=backoff)


def test_capability_based_selection_is_deterministic() -> None:
    cheap_tools = FakeAdapter("tools-a", capabilities=frozenset({
        ModelCapability.CHAT,
        ModelCapability.TOOLS,
    }))
    expensive_tools = FakeAdapter("tools-b", capabilities=frozenset({
        ModelCapability.CHAT,
        ModelCapability.TOOLS,
    }))
    chat_only = FakeAdapter("chat-only")
    router = _router_with(
        (_metadata("chat-only", capabilities=("chat",), priority=0), chat_only),
        (
            _metadata(
                "tools-b",
                capabilities=("chat", "tools"),
                priority=1,
                input_cost=50.0,
                output_cost=50.0,
            ),
            expensive_tools,
        ),
        (
            _metadata(
                "tools-a",
                capabilities=("chat", "tools"),
                priority=1,
                input_cost=1.0,
                output_cost=1.0,
            ),
            cheap_tools,
        ),
    )

    plan = router.plan(_request(capabilities=("chat", "tools")))
    assert plan.provider_ids == ("tools-a", "tools-b")
    assert "chat-only" in plan.rejected
    assert any("missing capabilities" in reason for reason in plan.rejected["chat-only"])

    result = asyncio.run(router.invoke(_request(capabilities=("chat", "tools"))))
    assert result.ok
    assert result.selected_provider_id == "tools-a"
    assert result.fallback_provider_ids == ("tools-b",)
    assert cheap_tools.calls and not expensive_tools.calls
    assert not chat_only.calls


def test_fallback_order_is_stable_after_partial_provider_failure() -> None:
    primary = FakeAdapter(
        "alpha",
        fail_times=3,
        error=TransientProviderError(f"api_key={_SECRET}"),
    )
    backup = FakeAdapter("beta", text="backup-ok")
    router = _router_with(
        (_metadata("alpha", priority=0, max_attempts=2), primary),
        (_metadata("beta", priority=1), backup),
    )

    result = asyncio.run(router.invoke(_request(retry_attempts=2)))
    assert result.ok
    assert result.selected_provider_id == "beta"
    assert result.planned_provider_ids == ("alpha", "beta")
    assert [attempt.outcome for attempt in result.attempts] == ["error", "ok"]
    assert result.attempts[0].error_type == "TransientProviderError"
    payload = result.as_dict()
    assert _SECRET not in repr(payload)
    assert _SECRET not in repr(result.trace)
    assert primary.calls
    assert backup.calls


def test_timeout_falls_back_then_fails_closed_when_deadline_elapses() -> None:
    slow = FakeAdapter("slow", delay=0.25)
    fast = FakeAdapter("fast", text="fast-ok")
    router = _router_with(
        (_metadata("slow", priority=0, timeout_seconds=0.05), slow),
        (_metadata("fast", priority=1, timeout_seconds=0.5), fast),
    )

    recovered = asyncio.run(router.invoke(_request(timeout_seconds=1.0)))
    assert recovered.ok
    assert recovered.selected_provider_id == "fast"
    assert recovered.attempts[0].outcome == "timeout"

    lonely = FakeAdapter("lonely", delay=0.25)
    timeout_router = _router_with(
        (_metadata("lonely", adapter_name="lonely", timeout_seconds=0.05), lonely)
    )
    exhausted = asyncio.run(
        timeout_router.invoke(_request(request_id="req-timeout", timeout_seconds=0.05))
    )
    assert exhausted.status == "timeout"
    assert exhausted.selected_provider_id is None
    assert exhausted.response is None
    assert lonely.calls


def test_input_and_output_provider_limits_are_independent() -> None:
    adapter = FakeAdapter("tight")
    router = _router_with(
        (
            _metadata("tight", max_input_tokens=10, max_output_tokens=100),
            adapter,
        )
    )
    plan = router.plan(_request(estimated_input_tokens=10, max_output_tokens=100))
    assert plan.provider_ids == ("tight",)


def test_budget_exhaustion_fails_closed_without_calling_unaffordable_providers() -> None:
    expensive = FakeAdapter("gold")
    also_expensive = FakeAdapter("platinum")
    router = _router_with(
        (
            _metadata(
                "gold",
                priority=0,
                input_cost=1_000_000.0,
                output_cost=1_000_000.0,
            ),
            expensive,
        ),
        (
            _metadata(
                "platinum",
                priority=1,
                input_cost=2_000_000.0,
                output_cost=2_000_000.0,
            ),
            also_expensive,
        ),
    )

    result = asyncio.run(
        router.invoke(
            _request(
                budget=RouteBudget(max_cost=0.0000001, max_provider_attempts=2),
                estimated_input_tokens=100,
                max_output_tokens=100,
            )
        )
    )
    assert result.status == "budget_exhausted"
    assert result.selected_provider_id is None
    assert expensive.calls == []
    assert also_expensive.calls == []


def test_actual_usage_over_budget_is_not_reported_as_success() -> None:
    greedy = FakeAdapter(
        "greedy",
        usage=TokenUsage(input_tokens=100, output_tokens=100),
    )
    router = _router_with(
        (
            _metadata(
                "greedy",
                input_cost=1_000.0,
                output_cost=1_000.0,
            ),
            greedy,
        )
    )
    result = asyncio.run(
        router.invoke(
            _request(
                budget=RouteBudget(max_cost=0.01, max_provider_attempts=1),
                estimated_input_tokens=1,
                max_output_tokens=1,
            )
        )
    )
    assert result.status == "budget_exhausted"
    assert result.response is None
    assert result.attempts[0].outcome == "budget_exhausted"
    assert greedy.calls


def test_actual_output_usage_over_token_budget_is_not_reported_as_success() -> None:
    greedy = FakeAdapter(
        "greedy-output",
        usage=TokenUsage(input_tokens=1, output_tokens=11),
    )
    router = _router_with((_metadata("greedy-output"), greedy))
    result = asyncio.run(
        router.invoke(
            _request(
                budget=RouteBudget(
                    max_cost=1.0,
                    max_output_tokens=10,
                    max_provider_attempts=1,
                ),
                estimated_input_tokens=1,
                max_output_tokens=10,
            )
        )
    )
    assert result.status == "budget_exhausted"
    assert result.response is None
    assert result.attempts[0].outcome == "budget_exhausted"
    assert result.budget.remaining_output_tokens == 0
    assert greedy.calls


def test_malformed_provider_metadata_fails_closed_and_is_atomic() -> None:
    router = ModelRouter()
    adapter = FakeAdapter("ok")
    router.register(_metadata("ok"), adapter)
    before = router.catalog()

    with pytest.raises(ProviderMetadataError, match="unknown keys"):
        router.register({**_metadata("bad"), "api_key": _SECRET}, FakeAdapter("bad"))
    with pytest.raises(ProviderMetadataError, match="missing keys"):
        router.register({"provider_id": "incomplete"}, FakeAdapter("incomplete"))
    with pytest.raises(ProviderMetadataError):
        router.register(
            {**_metadata("nan-cost"), "input_cost_per_million": math.nan},
            FakeAdapter("nan-cost"),
        )
    with pytest.raises(ProviderMetadataError):
        router.register(
            {**_metadata("caps-string"), "capabilities": "chat"},
            FakeAdapter("caps-string"),
        )
    with pytest.raises(ProviderMetadataError, match="normalized"):
        router.register(
            {**_metadata("caps-space"), "capabilities": (" chat",)},
            FakeAdapter("caps-space"),
        )
    with pytest.raises(ProviderMetadataError, match="normalized"):
        router.register(
            {**_metadata("caps-case"), "capabilities": ("CHAT",)},
            FakeAdapter("caps-case"),
        )
    with pytest.raises(ProviderMetadataError, match="adapter name"):
        router.register(_metadata("mismatch", adapter_name="other"), adapter)
    with pytest.raises(ProviderMetadataError, match="lacks claimed"):
        router.register(
            _metadata("overclaim", capabilities=("chat", "tools")),
            FakeAdapter("overclaim"),
        )

    assert router.catalog() == before
    assert asyncio.run(router.invoke(_request())).selected_provider_id == "ok"


def test_traces_and_eval_contract_keep_secrets_and_provenance() -> None:
    adapter = FakeAdapter("traceable", text="routed-answer")
    router = _router_with(
        (_metadata("traceable", capabilities=("chat", "code")), adapter)
    )
    request = _request(
        metadata={"api_key": _SECRET, "task": "summarize"},
        capabilities=("chat", "code"),
    )
    result = asyncio.run(router.invoke(request))
    assert result.ok
    assert result.trace["caller_metadata"]["api_key"] == REDACTED
    assert result.trace["caller_metadata"]["task"] == "summarize"
    assert _SECRET not in repr(result.as_dict())
    assert result.provenance.content_sha256
    assert result.provenance.operation == "model_route"
    assert result.provenance.actor == "traceable"
    assert result.provenance.metadata["request_id"] == "req-1"

    report = asyncio.run(
        RouteEvalContract().run(
            router,
            (
                RouteEvalCase(
                    case_id="select-code",
                    request=_request(
                        request_id="req-eval",
                        capabilities=("chat", "code"),
                        metadata={"token": _SECRET},
                    ),
                    expect_status="ok",
                    expect_provider_id="traceable",
                    expect_capabilities=frozenset({"chat", "code"}),
                    forbid_secret_fragments=(_SECRET,),
                ),
            ),
        )
    )
    assert report.passed
    assert report.verdicts[0].result.trace["caller_metadata"]["token"] == REDACTED


def test_disabled_and_duplicate_registration_rules() -> None:
    router = ModelRouter()
    adapter = FakeAdapter("shared")
    router.register(_metadata("primary", adapter_name="shared", priority=0), adapter)
    router.register(
        _metadata(
            "shadow",
            adapter_name="shared",
            model="shadow-model",
            priority=1,
            enabled=False,
        ),
        adapter,
    )
    with pytest.raises(ProviderMetadataError, match="already registered"):
        router.register(_metadata("primary", adapter_name="shared"), adapter)

    plan = router.plan(_request())
    assert plan.provider_ids == ("primary",)
    assert plan.rejected["shadow"] == ("disabled",)
