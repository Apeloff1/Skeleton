"""AI compiler, critic, router, candidates, consensus, and schema tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.candidates import CandidateSelector
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.consensus import ProposalConsensus, proposal_shape_digest
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.guardrails import ModelOutputGuard
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.schema import action_schema, model_response_schema, schema_digest
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal, IntentConstraint, IntentKind
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec


def catalog():
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable, tags=frozenset({"test", "inspect"})),
                ArgumentPolicy.allow_any(),
                description="Run bounded Python tooling.",
            ),
            CommandDefinition(
                ExecutableSpec("pywrite", sys.executable, tags=frozenset({"write", "repair"})),
                ArgumentPolicy.allow_any(),
                description="Run bounded write tooling.",
            ),
        )
    )


def effects():
    return EffectRegistry(
        (
            EffectContract(
                "python",
                frozenset({EffectKind.READ_FILESYSTEM, EffectKind.PROCESS_CONTROL}),
                idempotent=True,
                reversible=True,
            ),
            EffectContract(
                "pywrite",
                frozenset({EffectKind.WRITE_FILESYSTEM, EffectKind.PROCESS_CONTROL}),
                idempotent=False,
                reversible=True,
                compensation_command="python",
            ),
        )
    )


def intent(**changes):
    values = dict(
        intent_id="i",
        goal="Run bounded verification.",
        kind=IntentKind.TEST,
        constraint=IntentConstraint(
            max_steps=8,
            allow_network=False,
            allow_writes=False,
            allow_destructive=False,
        ),
    )
    values.update(changes)
    return AIIntent(**values)


def proposal(command="python", **changes):
    values = dict(
        proposal_id="p",
        intent_id="i",
        actions=(AIAction("a", command, ("-V",)),),
        confidence=0.95,
        uncertainty=0.05,
        model_id="m",
    )
    values.update(changes)
    return AIPlanProposal(**values)


def test_ai_tool_catalog_hides_executable_path():
    tools = AIToolCatalog(catalog())
    payload = tools.model_payload()
    assert payload
    serialized = str(payload)
    assert sys.executable not in serialized


def test_ai_tool_catalog_digest_stable():
    tools = AIToolCatalog(catalog())
    assert len(tools.digest) == 64
    assert tools.digest == tools.digest


def test_router_prefers_test_tag():
    tools = AIToolCatalog(catalog())
    routed = AIToolRouter(tools, effects()).route(intent())
    assert routed[0].card.name == "python"
    assert routed[0].score > routed[1].score


def test_router_respects_command_allowlist():
    item = intent(
        constraint=IntentConstraint(
            allowed_commands=frozenset({"python"}),
            allow_writes=True,
        )
    )
    routed = AIToolRouter(AIToolCatalog(catalog()), effects()).route(item)
    assert [entry.card.name for entry in routed] == ["python"]


def test_router_penalizes_write_when_disallowed():
    routed = AIToolRouter(AIToolCatalog(catalog()), effects()).route(intent())
    scores = {item.card.name: item.score for item in routed}
    assert scores["pywrite"] < scores["python"]


def test_compiler_creates_execution_plan():
    compiler = AIPlanCompiler(effects())
    compiled = compiler.compile(intent(), proposal())
    assert compiled.plan.plan_id == "p"
    assert compiled.plan.steps[0].command.command == "python"
    assert compiled.proposal_fingerprint == proposal().fingerprint


def test_compiler_rejects_intent_mismatch():
    compiler = AIPlanCompiler(effects())
    with pytest.raises(ValueError):
        compiler.compile(intent(intent_id="other"), proposal())


def test_compiler_rejects_disallowed_command():
    restricted = intent(
        constraint=IntentConstraint(allowed_commands=frozenset({"python"}))
    )
    compiler = AIPlanCompiler(effects())
    with pytest.raises(ValueError):
        compiler.compile(restricted, proposal("pywrite"))


def test_compiler_rejects_timeout_above_intent():
    limited = intent(constraint=IntentConstraint(max_timeout_seconds=1))
    item = proposal(
        actions=(AIAction("a", "python", ("-V",), timeout_seconds=2),)
    )
    with pytest.raises(ValueError):
        AIPlanCompiler(effects()).compile(limited, item)


def test_compiler_resolves_opaque_environment_refs():
    def resolve(action_id, key, ref):
        assert action_id == "a"
        assert key == "TOKEN"
        assert ref == "secret/token"
        return "resolved"

    item = proposal(
        actions=(
            AIAction(
                "a",
                "python",
                ("-V",),
                environment_refs={"TOKEN": "secret/token"},
            ),
        )
    )
    compiled = AIPlanCompiler(effects(), environment_resolver=resolve).compile(
        intent(), item
    )
    assert compiled.plan.steps[0].command.env == {"TOKEN": "resolved"}
    assert compiled.environment_references == ("secret/token",)


def test_compiler_missing_environment_resolver_fails():
    item = proposal(
        actions=(
            AIAction(
                "a",
                "python",
                environment_refs={"TOKEN": "secret/token"},
            ),
        )
    )
    with pytest.raises(ValueError):
        AIPlanCompiler(effects()).compile(intent(), item)


def test_compiler_cycle_is_rejected_by_execution_plan():
    item = proposal(
        actions=(
            AIAction("a", "python", depends_on=frozenset({"b"})),
            AIAction("b", "python", depends_on=frozenset({"a"})),
        )
    )
    with pytest.raises(ValueError):
        AIPlanCompiler(effects()).compile(intent(), item)


def test_critic_accepts_low_risk_autonomous_plan():
    policy = AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS)
    report = AIPlanCritic(effects(), policy).critique(intent(), proposal())
    assert report.guardrails.ok
    assert report.policy.allowed
    assert report.accepted_for_execution


def test_critic_marks_unknown_effect_as_error():
    report = AIPlanCritic(
        EffectRegistry(),
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
    ).critique(intent(), proposal())
    assert not report.accepted_for_execution
    assert any(item.code == "unknown_effect_contract" for item in report.findings)


def test_critic_cannot_be_overridden_by_model_critic():
    class FakeModel:
        model_id = "fake"
        capabilities = type("Caps", (), {"structured_output": True, "tool_use": True})()

        def critique(self, request, response):
            return {"verdict": "approve"}

    policy = AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS)
    critic = AIPlanCritic(EffectRegistry(), policy, model=FakeModel())
    report = critic.critique(intent(), proposal(), request=object(), response=object())
    assert not report.accepted_for_execution


def test_candidate_selector_picks_safer_candidate():
    effect_registry = effects()
    policy = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        max_uncertainty=1.0,
    )
    selector = CandidateSelector(AIPlanCritic(effect_registry, policy))
    safe = proposal(
        proposal_id="safe",
        confidence=0.9,
        uncertainty=0.05,
    )
    risky_intent = intent(
        constraint=IntentConstraint(max_steps=8, allow_writes=True)
    )
    risky = proposal(
        proposal_id="write",
        actions=(AIAction("a", "pywrite"),),
        confidence=0.99,
        uncertainty=0.01,
    )
    selection = selector.evaluate(risky_intent, (risky, safe))
    assert selection.selected is not None
    assert selection.selected.proposal.proposal_id == "safe"


def test_candidate_selector_deduplicates_identical_fingerprint():
    selector = CandidateSelector(
        AIPlanCritic(
            effects(),
            AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
        )
    )
    item = proposal()
    selection = selector.evaluate(intent(), (item, item))
    assert len(selection.candidates) == 1


def test_consensus_same_shape_reaches_threshold():
    first = proposal(proposal_id="p1", model_id="m1")
    second = proposal(proposal_id="p2", model_id="m2")
    report = ProposalConsensus().evaluate((first, second), threshold=2)
    assert report.reached
    assert report.groups[0].votes == 2


def test_consensus_different_args_do_not_group():
    first = proposal(proposal_id="p1", actions=(AIAction("a", "python", ("a",)),))
    second = proposal(proposal_id="p2", actions=(AIAction("a", "python", ("b",)),))
    report = ProposalConsensus().evaluate((first, second), threshold=2)
    assert not report.reached
    assert len(report.groups) == 2


def test_consensus_shape_ignores_model_id():
    first = proposal(model_id="one")
    second = proposal(proposal_id="other", model_id="two")
    assert proposal_shape_digest(first) == proposal_shape_digest(second)


def test_action_schema_disallows_extra_properties():
    assert action_schema()["additionalProperties"] is False


def test_response_schema_is_versioned_and_strict():
    schema = model_response_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["protocol_version"]["const"] == 1
    assert len(schema_digest()) == 64
