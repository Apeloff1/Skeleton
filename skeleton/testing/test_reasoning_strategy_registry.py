from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from skeleton.intelligence.cognitive_runtime import (
    CognitiveRuntimeError,
    ReasoningProgress,
    StopAction,
    build_reasoning_policy_receipt,
    evaluate_reasoning_progress,
)
from skeleton.intelligence.strategy_registry import (
    ReasoningBudget,
    ReasoningRequestProfile,
    ReasoningStrategyError,
    load_reasoning_strategy_registry,
    registry_from_payload,
    select_reasoning_strategy,
)


REGISTRY_PATH = Path("machine/p1_reasoning_strategy_registry.json")


def _registry():
    return load_reasoning_strategy_registry(REGISTRY_PATH)


def _budget(
    *,
    iterations: int = 10,
    candidates: int = 20,
    retrieval_rounds: int = 4,
    tool_calls: int = 2,
    cost: float = 5.0,
    wall_seconds: float = 300.0,
) -> ReasoningBudget:
    return ReasoningBudget(
        iterations=iterations,
        candidates=candidates,
        retrieval_rounds=retrieval_rounds,
        tool_calls=tool_calls,
        cost=cost,
        wall_seconds=wall_seconds,
    )


def _selection(
    *capabilities: str,
    budget: ReasoningBudget | None = None,
):
    registry = _registry()
    request = ReasoningRequestProfile(
        request_id="reason-1",
        required_capabilities=tuple(capabilities),
        budget=budget or _budget(),
    )
    return registry, select_reasoning_strategy(registry, request)


def _progress(
    strategy_id: str,
    *,
    iterations: int = 1,
    candidates: int = 1,
    retrieval_rounds: int = 0,
    tool_calls: int = 0,
    cost: float = 0.10,
    wall_seconds: float = 1.0,
    evidence_gain: float = 0.20,
    value_of_information: float = 0.20,
    uncertainty: float = 0.20,
    completed: bool = False,
    verified: bool = False,
) -> ReasoningProgress:
    return ReasoningProgress(
        request_id="reason-1",
        strategy_id=strategy_id,
        iterations=iterations,
        candidates=candidates,
        retrieval_rounds=retrieval_rounds,
        tool_calls=tool_calls,
        cost=cost,
        wall_seconds=wall_seconds,
        evidence_gain=evidence_gain,
        value_of_information=value_of_information,
        uncertainty=uncertainty,
        completed=completed,
        verified=verified,
    )


def test_registry_loads_five_bounded_strategies() -> None:
    registry = _registry()

    assert len(registry.strategies) == 5
    assert len(registry.digest) == 64
    assert registry.task_id == "P1-INTEL-03"
    assert registry.accountability_ref == "ACC-P1-INTEL-03"
    assert {
        item.strategy_id for item in registry.strategies
    } == {
        "direct_verified",
        "retrieve_then_reason",
        "bounded_search",
        "plan_then_verify",
        "ensemble_then_abstain",
    }


@pytest.mark.parametrize(
    ("capability", "expected"),
    (
        ("direct", "direct_verified"),
        ("retrieval", "retrieve_then_reason"),
        ("search", "bounded_search"),
        ("planning", "plan_then_verify"),
        ("ensemble", "ensemble_then_abstain"),
    ),
)
def test_strategy_selection_is_capability_driven_and_deterministic(
    capability: str,
    expected: str,
) -> None:
    registry, selection = _selection(capability, "verification")

    assert selection.strategy_id == expected
    assert selection.registry_digest == registry.digest
    assert len(selection.digest) == 64


def test_request_budget_tightens_registry_ceiling() -> None:
    registry, selection = _selection(
        "retrieval",
        "verification",
        budget=_budget(
            iterations=2,
            candidates=2,
            retrieval_rounds=1,
            tool_calls=0,
            cost=0.5,
            wall_seconds=30.0,
        ),
    )

    assert selection.strategy_id == "retrieve_then_reason"
    assert selection.effective_budget == ReasoningBudget(
        iterations=2,
        candidates=2,
        retrieval_rounds=1,
        tool_calls=0,
        cost=0.5,
        wall_seconds=30.0,
    )
    assert selection.effective_budget.cost < registry.by_id(
        "retrieve_then_reason"
    ).limits.cost


def test_zero_capability_dimensions_do_not_stop_at_zero_usage() -> None:
    registry, selection = _selection("direct", "verification")
    decision = evaluate_reasoning_progress(
        registry,
        selection,
        _progress(
            selection.strategy_id,
            iterations=0,
            candidates=0,
            retrieval_rounds=0,
            tool_calls=0,
            cost=0.0,
            wall_seconds=0.0,
            evidence_gain=0.2,
            value_of_information=0.2,
            uncertainty=0.2,
        ),
    )

    assert decision.action is StopAction.CONTINUE
    assert "retrieval_rounds" not in decision.reached_dimensions
    assert "tool_calls" not in decision.reached_dimensions


def test_no_eligible_strategy_fails_closed() -> None:
    registry = _registry()
    request = ReasoningRequestProfile(
        request_id="reason-1",
        required_capabilities=("quantum_oracle",),
        budget=_budget(),
    )

    with pytest.raises(ReasoningStrategyError, match="no eligible"):
        select_reasoning_strategy(registry, request)


def test_hard_budget_reached_is_compliant_terminal_stop() -> None:
    registry, selection = _selection("retrieval", "verification")
    limit = selection.effective_budget
    progress = _progress(
        selection.strategy_id,
        iterations=limit.iterations,
        candidates=1,
        retrieval_rounds=1,
        cost=0.2,
        wall_seconds=2.0,
    )

    decision = evaluate_reasoning_progress(registry, selection, progress)
    receipt = build_reasoning_policy_receipt(
        registry,
        selection,
        progress,
    )

    assert decision.action is StopAction.STOP_BUDGET
    assert decision.policy_compliant is True
    assert receipt.eligible_for_promotion is True
    assert receipt.evidence_ref().category == "reasoning_strategy_stop"


def test_crossing_hard_budget_is_policy_violation() -> None:
    registry, selection = _selection("search", "verification")
    limit = selection.effective_budget
    progress = _progress(
        selection.strategy_id,
        iterations=limit.iterations + 1,
    )

    decision = evaluate_reasoning_progress(registry, selection, progress)
    receipt = build_reasoning_policy_receipt(
        registry,
        selection,
        progress,
    )

    assert decision.action is StopAction.POLICY_VIOLATION
    assert decision.exceeded_dimensions == ("iterations",)
    assert receipt.policy_compliant is False
    assert receipt.eligible_for_promotion is False
    with pytest.raises(CognitiveRuntimeError, match="cannot become"):
        receipt.evidence_ref()


def test_low_evidence_gain_and_low_voi_stop_diminishing_returns() -> None:
    registry, selection = _selection("search", "verification")
    progress = _progress(
        selection.strategy_id,
        iterations=2,
        candidates=2,
        evidence_gain=0.01,
        value_of_information=0.01,
        uncertainty=0.30,
    )

    decision = evaluate_reasoning_progress(registry, selection, progress)

    assert decision.action is StopAction.STOP_DIMINISHING_RETURNS
    assert decision.reason == "low_evidence_gain_and_value_of_information"


def test_high_uncertainty_without_evidence_gain_abstains() -> None:
    registry, selection = _selection("ensemble", "verification")
    progress = _progress(
        selection.strategy_id,
        iterations=1,
        candidates=4,
        evidence_gain=0.0,
        value_of_information=0.5,
        uncertainty=0.90,
    )

    decision = evaluate_reasoning_progress(registry, selection, progress)

    assert decision.action is StopAction.ABSTAIN_UNCERTAIN
    assert decision.reason == "uncertainty_without_evidence_gain"


def test_verified_completion_is_successful_terminal_stop() -> None:
    registry, selection = _selection("planning", "verification")
    progress = _progress(
        selection.strategy_id,
        completed=True,
        verified=True,
    )

    decision = evaluate_reasoning_progress(registry, selection, progress)
    receipt = build_reasoning_policy_receipt(
        registry,
        selection,
        progress,
    )

    assert decision.action is StopAction.STOP_SUCCESS
    assert receipt.eligible_for_promotion is True
    assert len(receipt.receipt_digest) == 64


def test_unverified_completion_abstains_instead_of_self_finalizing() -> None:
    registry, selection = _selection("planning", "verification")
    progress = _progress(
        selection.strategy_id,
        completed=True,
        verified=False,
    )

    decision = evaluate_reasoning_progress(registry, selection, progress)

    assert decision.action is StopAction.ABSTAIN_UNVERIFIED
    assert decision.policy_compliant is True


def test_nonterminal_continue_cannot_become_promotion_evidence() -> None:
    registry, selection = _selection("search", "verification")
    progress = _progress(
        selection.strategy_id,
        evidence_gain=0.5,
        value_of_information=0.5,
        uncertainty=0.1,
    )
    receipt = build_reasoning_policy_receipt(
        registry,
        selection,
        progress,
    )

    assert receipt.action == "continue"
    assert receipt.terminal is False
    assert receipt.eligible_for_promotion is False
    with pytest.raises(CognitiveRuntimeError, match="cannot become"):
        receipt.evidence_ref()


def test_stale_registry_selection_is_rejected() -> None:
    registry, selection = _selection("search", "verification")
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["registry_version"] = "1.0.1"
    changed = registry_from_payload(payload)
    progress = _progress(selection.strategy_id)

    assert changed.digest != registry.digest
    with pytest.raises(CognitiveRuntimeError, match="registry digest is stale"):
        evaluate_reasoning_progress(changed, selection, progress)


def test_registry_mutation_changes_identity() -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    original = registry_from_payload(payload)
    changed_payload = json.loads(json.dumps(payload))
    changed_payload["strategies"][0]["limits"]["cost"] = 0.20
    changed = registry_from_payload(changed_payload)

    assert original.digest != changed.digest


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("evidence_gain", -0.1),
        ("value_of_information", 1.1),
        ("uncertainty", float("nan")),
        ("cost", -1.0),
        ("wall_seconds", float("inf")),
    ),
)
def test_progress_rejects_invalid_measurements(
    field: str,
    value: float,
) -> None:
    kwargs = {
        "strategy_id": "bounded_search",
        field: value,
    }
    with pytest.raises(CognitiveRuntimeError):
        _progress(**kwargs)


def test_verified_without_completed_is_rejected() -> None:
    with pytest.raises(CognitiveRuntimeError, match="also be completed"):
        _progress(
            "bounded_search",
            verified=True,
            completed=False,
        )


def test_self_confidence_text_is_never_part_of_policy_contract() -> None:
    registry, selection = _selection("search", "verification")
    progress = _progress(selection.strategy_id)
    rendered = repr(
        {
            "registry": registry.as_dict(),
            "selection": selection.as_dict(),
            "progress": progress.signal_dict(),
        }
    )

    assert "candidate text" not in rendered
    assert "model answer" not in rendered
    assert "self_confidence" not in rendered
