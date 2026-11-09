"""Planning-only eval, red-team, and regression-history tests."""

from __future__ import annotations

import sys

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.eval_dataset import AIEvalCase, AIEvalDataset
from skeleton.shells.ai.eval_runner import AIEvalCaseResult, AIEvalRun, AIEvalRunner
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.red_team import AIRedTeamRunner, default_red_team_cases
from skeleton.shells.ai.regression import AIRegressionHistory
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
                reversible=True,
                idempotent=True,
            ),
        )
    )


def planner():
    from skeleton.shells.ai.protocol import AIModelResponse

    def propose(request):
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                "p-" + request.intent.intent_id,
                request.intent.intent_id,
                (AIAction("a", "python"),),
                confidence=0.9,
                uncertainty=0.1,
                model_id="m",
            ),
        )

    tools = AIToolCatalog(catalog())
    policy = AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS)
    return AIPlanner(
        CallableAIModelPort("m", propose),
        tools,
        AIToolRouter(tools, effects()),
        policy_fingerprint=policy.fingerprint,
    ), policy


def test_eval_dataset_digest_stable():
    case = AIEvalCase("c", AIIntent("i", "inspect"))
    dataset = AIEvalDataset("d", 1, (case,))
    assert len(dataset.digest) == 64
    assert dataset.digest == dataset.digest


def test_eval_dataset_duplicate_case_rejected():
    import pytest
    case = AIEvalCase("c", AIIntent("i", "inspect"))
    with pytest.raises(ValueError):
        AIEvalDataset("d", 1, (case, case))


def test_eval_runner_passes_matching_case():
    item, policy = planner()
    dataset = AIEvalDataset(
        "d",
        1,
        (
            AIEvalCase(
                "c",
                AIIntent("i", "inspect"),
                required_commands=frozenset({"python"}),
                required_effects=frozenset({EffectKind.READ_FILESYSTEM}),
            ),
        ),
    )
    run = AIEvalRunner(
        item,
        AIPlanCritic(effects(), policy),
        effects(),
    ).run(dataset)
    assert run.pass_rate == 1.0


def test_eval_runner_fails_forbidden_command_expectation():
    item, policy = planner()
    dataset = AIEvalDataset(
        "d",
        1,
        (
            AIEvalCase(
                "c",
                AIIntent("i", "inspect"),
                forbidden_commands=frozenset({"python"}),
            ),
        ),
    )
    run = AIEvalRunner(
        item,
        AIPlanCritic(effects(), policy),
        effects(),
    ).run(dataset)
    assert run.failed == 1
    assert "forbidden commands present" in run.cases[0].reasons[0]


def test_eval_runner_never_executes_shell():
    item, policy = planner()
    dataset = AIEvalDataset(
        "d",
        1,
        (AIEvalCase("c", AIIntent("i", "inspect")),),
    )
    run = AIEvalRunner(
        item,
        AIPlanCritic(effects(), policy),
        effects(),
    ).run(dataset)
    assert run.cases[0].proposal_fingerprint


def test_red_team_default_cases_all_detected():
    results = AIRedTeamRunner().run(default_red_team_cases())
    assert all(item.passed for item in results)


def fake_run(pass_values):
    cases = tuple(
        AIEvalCaseResult(
            f"c{index}",
            passed,
            (),
            str(index) * 64,
            0,
            False,
            1,
        )
        for index, passed in enumerate(pass_values, start=1)
    )
    return AIEvalRun("d", 1, "a" * 64, "m", cases)


def test_regression_compare_detects_case_regression():
    baseline = fake_run((True, True))
    current = fake_run((False, True))
    report = AIRegressionHistory.compare(current, baseline)
    assert report.regressed
    assert report.regressed_cases == ("c1",)


def test_regression_compare_detects_improvement():
    baseline = fake_run((False, True))
    current = fake_run((True, True))
    report = AIRegressionHistory.compare(current, baseline)
    assert report.improved_cases == ("c1",)
    assert report.delta > 0


def test_regression_history_bounded():
    history = AIRegressionHistory(max_runs=1)
    first = fake_run((True,))
    second = fake_run((False,))
    history.record(first)
    history.record(second)
    assert len(history.snapshot()) == 1
    assert history.snapshot()[0].run == second
