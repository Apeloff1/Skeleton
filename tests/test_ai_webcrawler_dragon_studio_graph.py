"""Studio graph integration and scale boundary tests."""
import pytest
from skeleton.ai.webcrawler.dragon_labyrinth import (
    DragonLabyrinth, WorkKind,
)
from skeleton.ai.webcrawler.dragon_studio_graph import (
    StudioScale, create_studio_plan,
)
import sqlite3


def test_studio_graph_contains_full_learning_chain():
    plan = create_studio_plan(
        "alice", authorized=True,
        scale=StudioScale(design_rounds=2, playtest_rounds=2),
    )
    kinds = {node.kind for node in plan.nodes}
    assert WorkKind.TEMPORAL_ANALYSIS in kinds
    assert WorkKind.CAUSAL_CHALLENGE in kinds
    assert WorkKind.TASTE_CONFIRMATION in kinds
    assert WorkKind.ORIGINALITY_REVIEW in kinds
    assert WorkKind.ADVERSARIAL_CRITIQUE in kinds
    assert WorkKind.PROTOTYPE_BUILD in kinds
    assert WorkKind.RELEASE_REVIEW in kinds


def test_competing_branches_join_before_next_round():
    plan = create_studio_plan(
        "alice", authorized=True,
        scale=StudioScale(design_rounds=2),
    )
    nodes = {node.key: node for node in plan.nodes}
    assert nodes["round.00000.critique"].dependencies == (
        "round.00000.a", "round.00000.b",
    )
    assert nodes["round.00001.a"].dependencies == ("round.00000.gate",)
    assert nodes["round.00001.b"].dependencies == ("round.00000.gate",)


def test_required_human_approvals():
    plan = create_studio_plan(
        "alice", authorized=True,
        scale=StudioScale(design_rounds=1),
    )
    approvals = {node.key for node in plan.nodes if node.approval_required}
    assert approvals == {
        "01.capture_consent", "06.taste",
        "08.originality", "10.release_review",
    }


def test_studio_graph_can_be_installed():
    plan = create_studio_plan(
        "alice", authorized=True,
        scale=StudioScale(design_rounds=3),
    )
    engine = DragonLabyrinth(sqlite3.connect(":memory:"))
    engine.install(plan, authorized=True)
    assert len(engine.status("alice", plan.plan_id, authorized=True)) == len(
        plan.nodes,
    )
    assert [node.key for node in engine.ready(
        "alice", plan.plan_id, authorized=True,
    )] == ["01.capture_consent"]


def test_large_scale_fails_budget_before_execution():
    with pytest.raises(ValueError, match="graph"):
        create_studio_plan(
            "alice", authorized=True,
            scale=StudioScale(design_rounds=3000, max_nodes=1000),
        )


def test_studio_plan_is_deterministic():
    scale = StudioScale(design_rounds=4, playtest_rounds=2)
    assert create_studio_plan(
        "alice", authorized=True, scale=scale,
    ) == create_studio_plan("alice", authorized=True, scale=scale)
