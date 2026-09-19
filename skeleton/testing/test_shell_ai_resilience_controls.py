"""Resilient planner, provider health, circuit, rate limit, and replanning tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.model_circuit import (
    ModelCircuitOpen,
    ModelCircuitPolicy,
    ModelCircuitRegistry,
    ModelCircuitState,
)
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.provider_health import (
    ProviderHealth,
    ProviderHealthPolicy,
    ProviderHealthRegistry,
)
from skeleton.shells.ai.rate_limit import AIModelRateLimit, AIModelRateLimiter
from skeleton.shells.ai.replanner import BoundedReplanner, ReplanStop
from skeleton.shells.ai.resilient_planner import ResilientAIPlanner
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec


def catalog():
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable, tags=frozenset({"inspect"})),
                ArgumentPolicy.allow_any(),
                description="python",
            ),
        )
    )


def effects():
    return EffectRegistry(
        (
            EffectContract(
                "python",
                frozenset({EffectKind.READ_FILESYSTEM}),
                idempotent=True,
                reversible=True,
            ),
        )
    )


def intent():
    return AIIntent("i", "inspect safely")


def response_for(request, *, proposal_id="p", command="python", confidence=0.9):
    from skeleton.shells.ai.protocol import AIModelResponse
    return AIModelResponse(
        request.request_id,
        AIPlanProposal(
            proposal_id,
            request.intent.intent_id,
            (AIAction("a", command),),
            confidence=confidence,
            uncertainty=0.05,
            model_id=proposal_id,
        ),
    )


def planner(model_id, proposer):
    tools = AIToolCatalog(catalog())
    model = CallableAIModelPort(model_id, proposer)
    policy = AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS)
    return AIPlanner(
        model,
        tools,
        AIToolRouter(tools, effects()),
        policy_fingerprint=policy.fingerprint,
    )


def test_provider_health_unknown_before_attempt():
    registry = ProviderHealthRegistry()
    assert registry.snapshot("m").state is ProviderHealth.UNKNOWN


def test_provider_health_success_becomes_healthy():
    registry = ProviderHealthRegistry()
    snapshot = registry.record_success("m", latency_ms=5)
    assert snapshot.state is ProviderHealth.HEALTHY
    assert snapshot.success_rate == 1.0


def test_provider_health_failure_degrades_before_threshold():
    registry = ProviderHealthRegistry(
        ProviderHealthPolicy(failure_threshold=3)
    )
    snapshot = registry.record_failure("m", error_type="Timeout")
    assert snapshot.state is ProviderHealth.DEGRADED


def test_provider_health_threshold_unhealthy():
    registry = ProviderHealthRegistry(
        ProviderHealthPolicy(failure_threshold=2)
    )
    registry.record_failure("m")
    snapshot = registry.record_failure("m")
    assert snapshot.state is ProviderHealth.UNHEALTHY


def test_provider_health_quarantine_and_restore():
    registry = ProviderHealthRegistry()
    assert registry.quarantine("m").state is ProviderHealth.QUARANTINED
    restored = registry.restore("m")
    assert restored.state in {ProviderHealth.UNKNOWN, ProviderHealth.HEALTHY}


def test_provider_health_latency_can_be_unhealthy():
    registry = ProviderHealthRegistry(
        ProviderHealthPolicy(
            degraded_latency_ms=10,
            unhealthy_latency_ms=20,
        )
    )
    snapshot = registry.record_success("m", latency_ms=30)
    assert snapshot.state is ProviderHealth.UNHEALTHY


def test_model_circuit_opens_on_threshold():
    now = [0.0]
    registry = ModelCircuitRegistry(
        ModelCircuitPolicy(failure_threshold=2, recovery_seconds=10),
        clock=lambda: now[0],
    )
    registry.failure("m")
    snapshot = registry.failure("m")
    assert snapshot.state is ModelCircuitState.OPEN
    with pytest.raises(ModelCircuitOpen):
        registry.allow("m")


def test_model_circuit_half_open_after_recovery():
    now = [0.0]
    registry = ModelCircuitRegistry(
        ModelCircuitPolicy(failure_threshold=1, recovery_seconds=10),
        clock=lambda: now[0],
    )
    registry.failure("m")
    now[0] = 10
    registry.allow("m")
    assert registry.snapshot("m").state is ModelCircuitState.HALF_OPEN


def test_model_circuit_success_closes_half_open():
    now = [0.0]
    registry = ModelCircuitRegistry(
        ModelCircuitPolicy(
            failure_threshold=1,
            recovery_seconds=1,
            half_open_successes=1,
        ),
        clock=lambda: now[0],
    )
    registry.failure("m")
    now[0] = 1
    registry.allow("m")
    snapshot = registry.success("m")
    assert snapshot.state is ModelCircuitState.CLOSED


def test_model_circuit_half_open_failure_reopens():
    now = [0.0]
    registry = ModelCircuitRegistry(
        ModelCircuitPolicy(failure_threshold=1, recovery_seconds=1),
        clock=lambda: now[0],
    )
    registry.failure("m")
    now[0] = 1
    registry.allow("m")
    snapshot = registry.failure("m")
    assert snapshot.state is ModelCircuitState.OPEN


def test_rate_limit_consumes_tokens():
    now = [0.0]
    limiter = AIModelRateLimiter(
        AIModelRateLimit(capacity=2, refill_per_second=1),
        clock=lambda: now[0],
    )
    limiter.require("m")
    limiter.require("m")
    with pytest.raises(RuntimeError):
        limiter.require("m")


def test_rate_limit_refills():
    now = [0.0]
    limiter = AIModelRateLimiter(
        AIModelRateLimit(capacity=1, refill_per_second=1),
        clock=lambda: now[0],
    )
    limiter.require("m")
    assert not limiter.inspect("m").allowed
    now[0] = 1
    assert limiter.inspect("m").allowed


def test_rate_limit_override():
    limiter = AIModelRateLimiter()
    limiter.set_limit("m", AIModelRateLimit(capacity=1, refill_per_second=0.1))
    limiter.require("m")
    with pytest.raises(RuntimeError):
        limiter.require("m")


def test_resilient_planner_falls_back_after_failure():
    bad = planner("bad", lambda request: (_ for _ in ()).throw(RuntimeError("down")))
    good = planner("good", lambda request: response_for(request, proposal_id="good"))
    resilient = ResilientAIPlanner((bad, good))
    result = resilient.propose(intent())
    assert result.result.response.proposal.proposal_id == "good"
    assert [item.status for item in result.attempts] == ["failed", "succeeded"]


def test_resilient_planner_skips_quarantined_provider():
    bad = planner("bad", lambda request: response_for(request, proposal_id="bad"))
    good = planner("good", lambda request: response_for(request, proposal_id="good"))
    health = ProviderHealthRegistry()
    health.quarantine("bad")
    resilient = ResilientAIPlanner((bad, good), health=health)
    result = resilient.propose(intent())
    assert result.result.response.proposal.proposal_id == "good"
    assert result.attempts[0].status == "quarantined"


def test_resilient_planner_prefers_healthy_provider():
    first = planner("first", lambda request: response_for(request, proposal_id="first"))
    second = planner("second", lambda request: response_for(request, proposal_id="second"))
    health = ProviderHealthRegistry()
    health.record_failure("first")
    health.record_success("second", latency_ms=1)
    resilient = ResilientAIPlanner((first, second), health=health)
    result = resilient.propose(intent())
    assert result.result.response.proposal.proposal_id == "second"


def test_resilient_planner_all_fail():
    first = planner("a", lambda request: (_ for _ in ()).throw(ValueError("a")))
    second = planner("b", lambda request: (_ for _ in ()).throw(ValueError("b")))
    with pytest.raises(RuntimeError):
        ResilientAIPlanner((first, second)).propose(intent())


def test_replanner_accepts_first_safe_proposal():
    item = planner("m", lambda request: response_for(request))
    critic = AIPlanCritic(
        effects(),
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
    )
    report = BoundedReplanner(item, critic).run(intent())
    assert report.stop is ReplanStop.ACCEPTED
    assert report.selected_round == 0


def test_replanner_duplicate_stops():
    item = planner("m", lambda request: response_for(request, command="other"))
    critic = AIPlanCritic(
        effects(),
        AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
            deny_unknown_effects=True,
        ),
    )
    report = BoundedReplanner(item, critic, max_rounds=3).run(intent())
    assert report.stop in {ReplanStop.POLICY_DENIED, ReplanStop.DUPLICATE}


def test_replanner_round_cap_validated():
    item = planner("m", lambda request: response_for(request))
    critic = AIPlanCritic(effects(), AIShellPolicy())
    with pytest.raises(ValueError):
        BoundedReplanner(item, critic, max_rounds=0)
