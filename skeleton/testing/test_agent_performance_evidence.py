from __future__ import annotations

import pytest

from skeleton.ai.agents.performance_evidence import (
    AgentEvidenceError,
    AgentIdentity,
    AgentMetric,
    AgentPerformanceLedger,
    AgentPerformanceRecord,
    build_outcome,
)


def identity(model: str = "model-a") -> AgentIdentity:
    return AgentIdentity("agent-1", "task-7", "cfg:abc", model)


def outcome():
    return build_outcome(
        completion=(1.0, ["receipt:done"]),
        correctness=(0.9, ["eval:correct"]),
        recovery=(1.0, ["trace:recovery"]),
        cost=(0.4, ["ledger:cost"]),
        human_intervention=(0.0, ["audit:human"]),
    )


def test_record_is_deterministic_and_identity_bound() -> None:
    a = AgentPerformanceRecord(identity(), outcome(), "2026-10-05T18:00:00Z", "eval-1", 0)
    b = AgentPerformanceRecord(identity(), outcome(), "2026-10-05T18:00:00Z", "eval-1", 0)
    assert a.digest == b.digest
    changed = AgentPerformanceRecord(identity("model-b"), outcome(), "2026-10-05T18:00:00Z", "eval-1", 0)
    assert changed.digest != a.digest


def test_every_dimension_requires_independent_evidence() -> None:
    with pytest.raises(AgentEvidenceError, match="evidence refs"):
        AgentMetric("correctness", 1.0, ())


def test_ledger_fails_closed_on_replay_or_broken_chain() -> None:
    ledger = AgentPerformanceLedger()
    first = AgentPerformanceRecord(identity(), outcome(), "2026-10-05T18:00:00Z", "eval-1", 0)
    ledger.append(first)
    replay = AgentPerformanceRecord(identity(), outcome(), "2026-10-05T18:01:00Z", "eval-1", 0)
    with pytest.raises(AgentEvidenceError, match="sequence"):
        ledger.append(replay)
    broken = AgentPerformanceRecord(identity(), outcome(), "2026-10-05T18:01:00Z", "eval-1", 1, "0" * 64)
    with pytest.raises(AgentEvidenceError, match="predecessor"):
        ledger.append(broken)


def test_comparison_rejects_cross_task_goodharting() -> None:
    ledger = AgentPerformanceLedger()
    first = AgentPerformanceRecord(identity(), outcome(), "2026-10-05T18:00:00Z", "eval-1", 0)
    ledger.append(first)
    other_identity = AgentIdentity("agent-1", "task-other", "cfg:abc", "model-a")
    second = AgentPerformanceRecord(other_identity, outcome(), "2026-10-05T18:01:00Z", "eval-1", 1, first.digest)
    ledger.append(second)
    with pytest.raises(AgentEvidenceError, match="same task"):
        ledger.compare(0, 1)


def test_valid_chain_compares_dimensions_separately() -> None:
    ledger = AgentPerformanceLedger()
    first = AgentPerformanceRecord(identity(), outcome(), "2026-10-05T18:00:00Z", "eval-1", 0)
    ledger.append(first)
    improved = build_outcome(
        completion=(1.0, ["receipt:done2"]),
        correctness=(1.0, ["eval:correct2"]),
        recovery=(1.0, ["trace:recovery2"]),
        cost=(0.3, ["ledger:cost2"]),
        human_intervention=(0.0, ["audit:human2"]),
    )
    second = AgentPerformanceRecord(identity(), improved, "2026-10-05T18:01:00Z", "eval-2", 1, first.digest)
    ledger.append(second)
    delta = ledger.compare(0, 1)
    assert delta["correctness"] == pytest.approx(0.1)
    assert delta["cost"] == pytest.approx(-0.1)
