from __future__ import annotations

from skeleton.jeeves.agent.adaptive_runtime import AdaptiveConfig, AdaptiveJeevesRuntime
from skeleton.jeeves.agent.frontier_runtime import FrontierJeevesAgentRuntime


def test_adaptive_runtime_inherits_hardened_frontier_runtime() -> None:
    assert issubclass(AdaptiveJeevesRuntime, FrontierJeevesAgentRuntime)


def test_adaptive_frontier_controls_default_on_and_bounded() -> None:
    config = AdaptiveConfig()

    assert config.enable_frontier_reasoning is True
    assert config.enable_self_consistency is True
    assert config.maximum_frontier_rounds == 2
    assert 0.0 <= config.frontier_escalation_min_budget <= 1.0
    assert config.fail_closed_on_evidence_gap is True
