"""Provider-diverse ensemble planner tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.candidates import CandidateSelector
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.ensemble_planner import (
    EnsembleAIPlanner,
    EnsembleMember,
    EnsemblePolicy,
)
from skeleton.shells.ai.model_circuit import ModelCircuitPolicy, ModelCircuitRegistry
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.protocol import AIModelResponse
from skeleton.shells.ai.provider_health import ProviderHealthRegistry
from skeleton.shells.ai.rate_limit import AIModelRateLimit, AIModelRateLimiter
from skeleton.shells.ai.robust_consensus import ConsensusPolicy, RobustProposalConsensus
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec


def catalog(extra=False):
    commands = [
        CommandDefinition(
            ExecutableSpec("python", sys.executable),
            ArgumentPolicy.allow_any(),
            description="python",
        )
    ]
    if extra:
        commands.append(
            CommandDefinition(
                ExecutableSpec("inspect", sys.executable),
                ArgumentPolicy.allow_any(),
                description="inspect",
            )
        )
    return AIToolCatalog(CommandCatalog(tuple(commands)))


def effects(extra=False):
    items = [
        EffectContract(
            "python",
            frozenset({EffectKind.READ_FILESYSTEM}),
            idempotent=True,
            reversible=True,
        )
    ]
    if extra:
        items.append(
            EffectContract(
                "inspect",
                frozenset({EffectKind.READ_FILESYSTEM}),
                idempotent=True,
                reversible=True,
            )
        )
    return EffectRegistry(tuple(items))


def policy():
    return AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )


def make_planner(
    model_id,
    *,
    args=("-V",),
    fail=False,
    item_catalog=None,
    item_effects=None,
    item_policy=None,
    confidence=0.9,
    uncertainty=0.1,
):
    item_catalog = item_catalog or catalog()
    item_effects = item_effects or effects()
    item_policy = item_policy or policy()

    def propose(request):
        if fail:
            raise RuntimeError("provider failed")
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                f"proposal-{model_id}",
                request.intent.intent_id,
                (
                    AIAction(
                        "a",
                        "python",
                        args,
                        timeout_seconds=1,
                    ),
                ),
                confidence=confidence,
                uncertainty=uncertainty,
                model_id=model_id,
            ),
        )

    model = CallableAIModelPort(model_id, propose)
    return AIPlanner(
        model,
        item_catalog,
        AIToolRouter(item_catalog, item_effects),
        policy_fingerprint=item_policy.fingerprint,
    )


def selector():
    return CandidateSelector(
        AIPlanCritic(
            effects(),
            policy(),
        )
    )


def ensemble(members, **kwargs):
    return EnsembleAIPlanner(
        tuple(members),
        selector(),
        **kwargs,
    )


def test_ensemble_two_models_same_shape_selects_candidate():
    service = ensemble(
        (
            EnsembleMember(make_planner("a"), "provider-a"),
            EnsembleMember(make_planner("b"), "provider-b"),
        )
    )
    result = service.propose(AIIntent("i", "inspect python"))
    assert result.consensus.reached
    assert len(result.results) == 2
    assert result.selected.response.proposal.model_id in {"a", "b"}
    assert result.selection.selected is not None


def test_ensemble_different_shapes_fail_consensus():
    service = ensemble(
        (
            EnsembleMember(make_planner("a", args=("-V",)), "provider-a"),
            EnsembleMember(make_planner("b", args=("--help",)), "provider-b"),
        )
    )
    with pytest.raises(RuntimeError, match="consensus"):
        service.propose(AIIntent("i", "inspect python"))


def test_ensemble_provider_diversity_policy():
    service = EnsembleAIPlanner(
        (
            EnsembleMember(make_planner("a"), "provider-one"),
            EnsembleMember(make_planner("b"), "provider-one"),
        ),
        selector(),
        consensus=RobustProposalConsensus(
            ConsensusPolicy(
                min_unique_models=2,
                min_unique_providers=2,
            )
        ),
    )
    with pytest.raises(RuntimeError, match="consensus"):
        service.propose(AIIntent("i", "inspect python"))


def test_ensemble_provider_failure_can_still_reach_consensus():
    service = EnsembleAIPlanner(
        (
            EnsembleMember(make_planner("bad", fail=True), "provider-bad"),
            EnsembleMember(make_planner("a"), "provider-a"),
            EnsembleMember(make_planner("b"), "provider-b"),
        ),
        selector(),
        policy=EnsemblePolicy(max_members=3, min_successes=2),
    )
    result = service.propose(AIIntent("i", "inspect python"))
    assert result.consensus.reached
    statuses = {item.model_id: item.status for item in result.attempts}
    assert statuses["bad"] == "failed"
    assert statuses["a"] == "succeeded"
    assert statuses["b"] == "succeeded"


def test_ensemble_not_enough_successes_fails_closed():
    service = EnsembleAIPlanner(
        (
            EnsembleMember(make_planner("bad", fail=True), "provider-bad"),
            EnsembleMember(make_planner("a"), "provider-a"),
        ),
        selector(),
        policy=EnsemblePolicy(max_members=2, min_successes=2),
    )
    with pytest.raises(RuntimeError, match="enough successful"):
        service.propose(AIIntent("i", "inspect python"))


def test_ensemble_quarantined_member_is_skipped():
    health = ProviderHealthRegistry()
    service = EnsembleAIPlanner(
        (
            EnsembleMember(make_planner("q"), "provider-q"),
            EnsembleMember(make_planner("a"), "provider-a"),
            EnsembleMember(make_planner("b"), "provider-b"),
        ),
        selector(),
        policy=EnsemblePolicy(max_members=3, min_successes=2),
        health=health,
    )
    health.quarantine("provider-q:q")
    result = service.propose(AIIntent("i", "inspect python"))
    assert any(
        item.model_id == "q" and item.status == "quarantined"
        for item in result.attempts
    )


def test_ensemble_open_circuit_skips_member():
    circuits = ModelCircuitRegistry(
        ModelCircuitPolicy(
            failure_threshold=1,
            recovery_seconds=1000,
        )
    )
    service = EnsembleAIPlanner(
        (
            EnsembleMember(make_planner("q"), "provider-q"),
            EnsembleMember(make_planner("a"), "provider-a"),
            EnsembleMember(make_planner("b"), "provider-b"),
        ),
        selector(),
        policy=EnsemblePolicy(max_members=3, min_successes=2),
        circuits=circuits,
    )
    circuits.failure("provider-q:q")
    result = service.propose(AIIntent("i", "inspect python"))
    assert any(
        item.model_id == "q" and item.status == "circuit_open"
        for item in result.attempts
    )


def test_ensemble_rate_limited_member_is_skipped():
    limiter = AIModelRateLimiter(
        AIModelRateLimit(capacity=1, refill_per_second=0.0001)
    )
    limiter.require("provider-q:q")
    service = EnsembleAIPlanner(
        (
            EnsembleMember(make_planner("q"), "provider-q"),
            EnsembleMember(make_planner("a"), "provider-a"),
            EnsembleMember(make_planner("b"), "provider-b"),
        ),
        selector(),
        policy=EnsemblePolicy(max_members=3, min_successes=2),
        rate_limiter=limiter,
    )
    result = service.propose(AIIntent("i", "inspect python"))
    assert any(
        item.model_id == "q" and item.status == "rate_limited"
        for item in result.attempts
    )


def test_ensemble_tool_catalog_mismatch_rejected():
    first_catalog = catalog()
    second_catalog = catalog(extra=True)
    with pytest.raises(ValueError, match="catalog"):
        EnsembleAIPlanner(
            (
                EnsembleMember(
                    make_planner(
                        "a",
                        item_catalog=first_catalog,
                        item_effects=effects(),
                    ),
                    "one",
                ),
                EnsembleMember(
                    make_planner(
                        "b",
                        item_catalog=second_catalog,
                        item_effects=effects(extra=True),
                    ),
                    "two",
                ),
            ),
            selector(),
        )


def test_ensemble_policy_fingerprint_mismatch_rejected():
    first_policy = policy()
    second_policy = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        max_actions=31,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )
    with pytest.raises(ValueError, match="policy"):
        EnsembleAIPlanner(
            (
                EnsembleMember(
                    make_planner("a", item_policy=first_policy),
                    "one",
                ),
                EnsembleMember(
                    make_planner("b", item_policy=second_policy),
                    "two",
                ),
            ),
            selector(),
        )


def test_ensemble_duplicate_provider_model_member_rejected():
    item = EnsembleMember(make_planner("a"), "provider")
    with pytest.raises(ValueError, match="duplicate"):
        EnsembleAIPlanner(
            (item, item),
            selector(),
        )


def test_ensemble_member_count_must_cover_min_successes():
    with pytest.raises(ValueError, match="fewer members"):
        EnsembleAIPlanner(
            (EnsembleMember(make_planner("a"), "one"),),
            selector(),
            policy=EnsemblePolicy(max_members=2, min_successes=2),
        )


def test_ensemble_max_members_limits_calls():
    calls = []

    def planner_with_call(model_id):
        item_catalog = catalog()
        item_effects = effects()
        item_policy = policy()

        def propose(request):
            calls.append(model_id)
            return AIModelResponse(
                request.request_id,
                AIPlanProposal(
                    f"p-{model_id}",
                    request.intent.intent_id,
                    (AIAction("a", "python", ("-V",)),),
                    confidence=0.9,
                    uncertainty=0.1,
                    model_id=model_id,
                ),
            )

        return AIPlanner(
            CallableAIModelPort(model_id, propose),
            item_catalog,
            AIToolRouter(item_catalog, item_effects),
            policy_fingerprint=item_policy.fingerprint,
        )

    service = EnsembleAIPlanner(
        tuple(
            EnsembleMember(planner_with_call(name), f"provider-{name}")
            for name in ("a", "b", "c")
        ),
        selector(),
        policy=EnsemblePolicy(max_members=2, min_successes=2),
    )
    service.propose(AIIntent("i", "inspect python"))
    assert len(calls) == 2


def test_ensemble_prior_observations_reach_every_successful_planner():
    observed = {}
    members = []
    for model_id in ("a", "b"):
        item_catalog = catalog()
        item_effects = effects()
        item_policy = policy()

        def make(model_id):
            def propose(request):
                observed[model_id] = request.prior_observations
                return AIModelResponse(
                    request.request_id,
                    AIPlanProposal(
                        f"p-{model_id}",
                        request.intent.intent_id,
                        (AIAction("a", "python", ("-V",)),),
                        confidence=0.9,
                        uncertainty=0.1,
                        model_id=model_id,
                    ),
                )
            return propose

        planner = AIPlanner(
            CallableAIModelPort(model_id, make(model_id)),
            item_catalog,
            AIToolRouter(item_catalog, item_effects),
            policy_fingerprint=item_policy.fingerprint,
        )
        members.append(EnsembleMember(planner, f"provider-{model_id}"))
    service = EnsembleAIPlanner(tuple(members), selector())
    service.propose(
        AIIntent("i", "inspect python"),
        prior_observations=({"kind": "context"},),
    )
    assert observed["a"] == ({"kind": "context"},)
    assert observed["b"] == ({"kind": "context"},)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_members": 0},
        {"min_successes": 0},
        {"max_members": 1, "min_successes": 2},
    ],
)
def test_ensemble_policy_validation(kwargs):
    with pytest.raises(ValueError):
        EnsemblePolicy(**kwargs)
