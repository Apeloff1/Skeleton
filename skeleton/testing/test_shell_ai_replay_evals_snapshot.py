"""AI shell diagnostics, policy-store, snapshot, eval, benchmark, and specialist tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.benchmark import default_benchmark_cases
from skeleton.shells.ai.budget import AIBudget
from skeleton.shells.ai.calibration import AICalibration
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.evals import AIShellEvaluator
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.memory import AIOutcomeMemory
from skeleton.shells.ai.model_port import CallableAIModelPort, ModelCapabilities
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_store import AIPolicyConflict, AIPolicyStore
from skeleton.shells.ai.snapshot import AIShellSnapshotter
from skeleton.shells.ai.specialists import PlannerSpecialist, SpecialistRegistry
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal, IntentKind
from skeleton.shells.ai.verifier import CriterionResult, VerificationReport, VerificationState
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec


def catalog():
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
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


def model():
    return CallableAIModelPort(
        "m",
        lambda request: {
            "protocol_version": 1,
            "request_id": request.request_id,
            "proposal": {
                "proposal_id": "p",
                "intent_id": request.intent.intent_id,
                "actions": [{"action_id": "a", "command": "python", "args": ["-V"]}],
                "confidence": 0.9,
                "uncertainty": 0.1,
                "model_id": "m",
            },
        },
    )


def test_ai_diagnostics_healthy_with_effect_coverage():
    report = AIShellDiagnostics(
        AIToolCatalog(catalog()),
        effects(),
        AIShellPolicy(),
        model(),
    ).inspect()
    assert report.ok


def test_ai_diagnostics_missing_effect_is_error_by_default():
    report = AIShellDiagnostics(
        AIToolCatalog(catalog()),
        EffectRegistry(),
        AIShellPolicy(),
        model(),
    ).inspect()
    assert not report.ok
    assert any(item.code == "missing_effect_contract" for item in report.findings)


def test_ai_diagnostics_unstructured_model_is_error():
    unstructured = CallableAIModelPort(
        "bad",
        lambda request: {},
        capabilities=ModelCapabilities(structured_output=False),
    )
    report = AIShellDiagnostics(
        AIToolCatalog(catalog()),
        effects(),
        AIShellPolicy(),
        unstructured,
    ).inspect()
    assert not report.ok


def test_ai_policy_store_cas():
    store = AIPolicyStore(AIShellPolicy())
    second = store.compare_and_swap(
        1,
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
    )
    assert second.revision == 2


def test_ai_policy_store_conflict():
    store = AIPolicyStore()
    store.replace(AIShellPolicy(autonomy=AutonomyMode.SUPERVISED))
    with pytest.raises(AIPolicyConflict):
        store.compare_and_swap(1, AIShellPolicy())


def test_ai_policy_store_history():
    store = AIPolicyStore()
    store.replace(AIShellPolicy(autonomy=AutonomyMode.SUPERVISED))
    assert [item.revision for item in store.history()] == [1, 2]


def test_ai_snapshot_digest_changes_with_journal():
    policy_store = AIPolicyStore()
    diagnostics = AIShellDiagnostics(
        AIToolCatalog(catalog()),
        effects(),
        policy_store.current().policy,
        model(),
    )
    journal = AIDecisionJournal()
    snapshotter = AIShellSnapshotter(
        policy_store=policy_store,
        diagnostics=diagnostics,
        budget=AIBudget(),
        calibration=AICalibration(),
        memory=AIOutcomeMemory(),
        journal=journal,
    )
    first = snapshotter.capture().digest
    journal.append("x", session_id="s", intent_id="i")
    second = snapshotter.capture().digest
    assert first != second


def test_ai_eval_rewards_verified_safe_plan():
    item_intent = AIIntent("i", "inspect")
    item_proposal = AIPlanProposal(
        "p",
        "i",
        (AIAction("a", "python"),),
        confidence=0.9,
        uncertainty=0.1,
    )
    critique = AIPlanCritic(
        effects(),
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
    ).critique(item_intent, item_proposal)
    verification = VerificationReport(
        (CriterionResult("x", VerificationState.PASSED, "ok", True),)
    )
    score = AIShellEvaluator().score_plan(
        item_intent,
        item_proposal,
        critique,
        verification=verification,
        actual_success=True,
    )
    assert score.aggregate > 0.5
    assert score.verification == 1.0


def test_ai_eval_penalizes_failed_verification():
    item_intent = AIIntent("i", "inspect")
    item_proposal = AIPlanProposal(
        "p",
        "i",
        (AIAction("a", "python"),),
        confidence=0.9,
        uncertainty=0.1,
    )
    critique = AIPlanCritic(
        effects(),
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
    ).critique(item_intent, item_proposal)
    verification = VerificationReport(
        (CriterionResult("x", VerificationState.FAILED, "bad", True),)
    )
    score = AIShellEvaluator().score_plan(
        item_intent,
        item_proposal,
        critique,
        verification=verification,
        actual_success=False,
    )
    assert score.verification == 0.0


def test_default_benchmark_cases_are_distinct():
    cases = default_benchmark_cases()
    ids = [case.case_id for case in cases]
    assert len(ids) == len(set(ids))
    assert len(cases) >= 4


def test_default_benchmark_has_deploy_denial_case():
    cases = {case.case_id: case for case in default_benchmark_cases()}
    assert "deploy" in cases["deny-deploy"].forbidden_commands


def test_specialist_registry_routes_by_intent():
    registry = SpecialistRegistry()
    planner = PlannerSpecialist(
        "tests",
        model(),
        frozenset({IntentKind.TEST}),
        priority=10,
    )
    analyzer = PlannerSpecialist(
        "analysis",
        model(),
        frozenset({IntentKind.ANALYZE}),
        priority=5,
    )
    registry.register(planner)
    registry.register(analyzer)
    routed = registry.route(AIIntent("i", "test", kind=IntentKind.TEST))
    assert [item.name for item in routed] == ["tests"]


def test_specialist_registry_priority_order():
    registry = SpecialistRegistry()
    registry.register(
        PlannerSpecialist("low", model(), frozenset({IntentKind.TEST}), priority=1)
    )
    registry.register(
        PlannerSpecialist("high", model(), frozenset({IntentKind.TEST}), priority=5)
    )
    assert [item.name for item in registry.route(AIIntent("i", "test", kind=IntentKind.TEST))] == [
        "high",
        "low",
    ]
