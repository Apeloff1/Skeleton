from __future__ import annotations

import pytest

from skeleton.cortex.adversarial import AdversarialContext, GateStatus
from skeleton.cortex.tri_adversarial import (
    TRI_FOCUS_GATES,
    TRI_LANES,
    TriAdversarialEngine,
    TriAdversarialReleaseBlocked,
    TriLane,
    evaluate_tri_creation,
    guard_tri_creation,
)


def _ctx(**overrides):
    values = {
        "request": "Create a deterministic game specification",
        "candidate": {"title": "Forge", "mechanics": ["combat", "progression"]},
    }
    values.update(overrides)
    return AdversarialContext(**values)


def test_tri_engine_runs_three_complete_100_gate_lanes() -> None:
    decision = TriAdversarialEngine().evaluate(_ctx())

    assert decision.allowed is True
    assert decision.score == 300.0
    assert decision.normalized_score == 100.0
    assert len(decision.lanes) == 3
    assert len(decision.results) == 300
    assert tuple(item.lane for item in decision.lanes) == TRI_LANES
    assert all(len(item.results) == 100 for item in decision.lanes)
    assert all(item.results[-1].gate_id == 100 for item in decision.lanes)
    assert all(item.results[-1].status is GateStatus.PASS for item in decision.lanes)
    assert decision.seal is not None


def test_one_failed_lane_blocks_combined_release_without_score_averaging() -> None:
    decision = TriAdversarialEngine().evaluate(
        _ctx(
            metadata={
                "tri_lanes": {
                    "quality": {
                        "adverse_signals": {"arithmetic_error": True},
                    }
                }
            }
        )
    )

    assert decision.allowed is False
    assert decision.seal is None
    assert decision.lane(TriLane.QUALITY).allowed is False
    assert decision.lane(TriLane.ADVERSARIAL_QUALITY).allowed is True
    assert decision.lane(TriLane.INTEGRITY).allowed is True
    assert any(
        result.lane is TriLane.QUALITY
        and result.gate_id == 31
        and result.status is GateStatus.BLOCK
        for result in decision.results
    )


def test_global_hard_block_is_seen_by_all_three_lanes() -> None:
    decision = TriAdversarialEngine().evaluate(
        _ctx(metadata={"adverse_signals": {"secret_detection": True}})
    )

    assert decision.allowed is False
    for lane in TRI_LANES:
        lane_decision = decision.lane(lane)
        gate91 = lane_decision.results[90]
        assert gate91.gate_id == 91
        assert gate91.status is GateStatus.BLOCK


def test_lane_metadata_is_isolated_and_merged_with_global_metadata() -> None:
    seen = []

    def judge(ctx, batch):
        if batch[0].gate_id == 1:
            seen.append(
                (
                    ctx.metadata["tri_lane"],
                    ctx.metadata["global_marker"],
                    ctx.metadata.get("lane_marker"),
                    tuple(ctx.metadata["tri_focus_gates"]),
                )
            )
        return {}

    engine = TriAdversarialEngine(judge=judge)
    decision = engine.evaluate(
        _ctx(
            metadata={
                "global_marker": "shared",
                "tri_lanes": {
                    "quality": {"lane_marker": "q"},
                    "adversarial_quality": {"lane_marker": "aq"},
                    "integrity": {"lane_marker": "i"},
                },
            }
        )
    )

    assert decision.allowed is True
    assert seen == [
        ("quality", "shared", "q", TRI_FOCUS_GATES[TriLane.QUALITY]),
        (
            "adversarial_quality",
            "shared",
            "aq",
            TRI_FOCUS_GATES[TriLane.ADVERSARIAL_QUALITY],
        ),
        ("integrity", "shared", "i", TRI_FOCUS_GATES[TriLane.INTEGRITY]),
    ]


def test_batched_judging_caps_at_ten_calls_per_lane() -> None:
    calls = []

    def judge(ctx, batch):
        calls.append((ctx.metadata["tri_lane"], tuple(spec.gate_id for spec in batch)))
        return {}

    decision = TriAdversarialEngine(judge=judge).evaluate(_ctx())

    assert decision.allowed is True
    assert len(calls) == 30
    for lane in TRI_LANES:
        lane_calls = [batch for seen_lane, batch in calls if seen_lane == lane.value]
        assert len(lane_calls) == 10
        assert lane_calls[0] == tuple(range(1, 11))
        assert lane_calls[-1] == tuple(range(91, 100))


def test_lane_specific_judge_can_block_only_its_lane() -> None:
    def adversarial_judge(ctx, batch):
        if any(spec.gate_id == 43 for spec in batch):
            return {43: {"status": "block", "reason": "false-premise attack succeeded"}}
        return {}

    engine = TriAdversarialEngine(
        judges={TriLane.ADVERSARIAL_QUALITY: adversarial_judge}
    )
    decision = engine.evaluate(_ctx())

    assert decision.allowed is False
    assert decision.lane(TriLane.QUALITY).allowed is True
    assert decision.lane(TriLane.ADVERSARIAL_QUALITY).allowed is False
    assert decision.lane(TriLane.INTEGRITY).allowed is True
    gate43 = decision.lane(TriLane.ADVERSARIAL_QUALITY).results[42]
    assert gate43.status is GateStatus.BLOCK
    assert gate43.reason == "false-premise attack succeeded"


def test_tri_seal_is_deterministic_and_lane_bound() -> None:
    engine = TriAdversarialEngine(seal_key=b"tri-test-key")

    first = engine.evaluate(_ctx())
    second = engine.evaluate(_ctx())

    assert first.allowed and second.allowed
    assert first.seal == second.seal
    assert first.seal.startswith("hmac-sha256:")
    lane_seals = [lane.decision.seal for lane in first.lanes]
    assert all(seal and seal.startswith("hmac-sha256:") for seal in lane_seals)
    assert len(set(lane_seals)) == 3


def test_public_evaluate_helper_returns_300_results() -> None:
    decision = evaluate_tri_creation(
        request="Create an NPC",
        candidate={"name": "Sentinel"},
        metadata={"creation_type": "npc"},
    )

    assert decision.allowed is True
    assert len(decision.results) == 300


def test_public_guard_returns_candidate_on_unanimous_release() -> None:
    candidate = {"name": "Sentinel"}

    assert guard_tri_creation(request="Create an NPC", candidate=candidate) == candidate


def test_public_guard_raises_with_full_tri_diagnostics() -> None:
    with pytest.raises(TriAdversarialReleaseBlocked) as exc:
        guard_tri_creation(
            request="Create output",
            candidate={"safe": True},
            metadata={"adverse_signals": {"context_poisoning": True}},
        )

    decision = exc.value.decision
    assert decision.allowed is False
    assert len(decision.results) == 300
    assert {result.lane for result in decision.blockers} == set(TRI_LANES)
