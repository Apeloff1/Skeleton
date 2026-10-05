from skeleton.school.code_intelligence import CodeIntelligenceEngine
from skeleton.school.cs_pathways import CSFamily, next_pathway, pathways_for
from skeleton.school.debugging import DebugAction, DebuggingPolicy
from skeleton.school.energy import EnergyBudget, EnergyStrategy, choose_energy_strategy


def test_debug_policy_prioritizes_security_and_regression_evidence():
    report = CodeIntelligenceEngine().analyze("eval(user_input)\ndef run():\n    return 1\n")
    plan = DebuggingPolicy().plan(report, error_context="ValueError: bad input")
    assert plan.hypotheses
    assert any(item.action == DebugAction.ISOLATE for item in plan.experiments)
    assert any(item.action == DebugAction.TEST for item in plan.experiments)


def test_debug_learning_signal_distinguishes_independence():
    policy = DebuggingPolicy()
    report = CodeIntelligenceEngine().analyze("def run():\n    return 1\n")
    plan = policy.plan(report)
    assert policy.learning_signal(plan, successful=True, explanation_quality=0.9) == "independent_debugging_evidence"
    assert policy.learning_signal(plan, successful=False) == "debugging_misconception_or_gap"


def test_cs_pathways_connect_concept_to_transfer():
    assert pathways_for(family=CSFamily.ALGORITHMS)
    first = next_pathway([])
    assert first is not None
    assert first.implementation
    assert first.transfer_question


def test_energy_budget_recovers_and_adapts_strategy():
    low = EnergyBudget(current=0.2)
    assert choose_energy_strategy(low).strategy == EnergyStrategy.LIGHT_REVIEW
    recovered = low.recover(5)
    assert recovered.current == 0.7
    assert choose_energy_strategy(recovered).strategy == EnergyStrategy.DEEP_WORK
