"""Stack graph and landing planner regressions for auto-merge."""

from __future__ import annotations

import pytest

from skeleton.pr_automation.automerge_model import StackRelation
from skeleton.pr_automation.automerge_stack import (
    ancestors,
    annotate_all,
    annotate_snapshot,
    build_stack_graph,
    descendants,
    landing_plan,
    leaf_nodes,
    root_for,
    stack_groups,
    validate_graph,
)
from skeleton.testing.automerge_test_support import (
    SHA_A,
    SHA_B,
    SHA_C,
    SHA_D,
    identity,
    snapshot,
)


def _root(number=1, head_ref="feature/root", head_sha=SHA_B):
    return snapshot(
        number=number,
        base_ref="main",
        base_sha=SHA_A,
        head_ref=head_ref,
        head_sha=head_sha,
    )


def _child(
    number=2,
    *,
    parent_ref="feature/root",
    parent_sha=SHA_B,
    head_ref="feature/child",
    head_sha=SHA_C,
):
    return snapshot(
        number=number,
        base_ref=parent_ref,
        base_sha=parent_sha,
        head_ref=head_ref,
        head_sha=head_sha,
    )


def test_single_root_graph():
    graph = build_stack_graph((_root(),), default_branch="main")
    assert graph.roots == (1,)
    assert graph.cycles == ()
    assert graph.orphans == ()
    node = graph.node(1)
    assert node is not None
    assert node.relation is StackRelation.ROOT
    assert node.depth == 0
    assert node.parent_pr is None


def test_root_and_child_graph():
    graph = build_stack_graph(
        (_root(), _child()),
        default_branch="main",
    )
    root = graph.node(1)
    child = graph.node(2)
    assert root is not None and child is not None
    assert root.children == (2,)
    assert child.parent_pr == 1
    assert child.relation is StackRelation.CHILD
    assert child.depth == 1


def test_three_level_stack_depths():
    root = _root()
    child = _child()
    grandchild = _child(
        number=3,
        parent_ref="feature/child",
        parent_sha=SHA_C,
        head_ref="feature/grandchild",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, child, grandchild), default_branch="main")
    assert graph.node(1).depth == 0
    assert graph.node(2).depth == 1
    assert graph.node(3).depth == 2


def test_orphan_is_detected():
    orphan = _child(parent_ref="missing/parent")
    graph = build_stack_graph((orphan,), default_branch="main")
    assert graph.orphans == (2,)
    assert graph.node(2).relation is StackRelation.ORPHAN
    assert graph.node(2).depth == -1


def test_duplicate_head_branch_is_detected():
    first = _root(number=1, head_ref="feature/shared")
    second = _root(number=2, head_ref="feature/shared", head_sha=SHA_C)
    graph = build_stack_graph((first, second), default_branch="main")
    assert graph.duplicate_heads == ("feature/shared",)


def test_duplicate_pr_numbers_rejected():
    one = _root(number=1)
    duplicate = _root(number=1, head_ref="feature/other", head_sha=SHA_C)
    with pytest.raises(ValueError, match="duplicate"):
        build_stack_graph((one, duplicate), default_branch="main")


def test_self_cycle_detected_when_pr_targets_own_head():
    item = snapshot(
        number=1,
        base_ref="feature/self",
        head_ref="feature/self",
    )
    graph = build_stack_graph((item,), default_branch="main")
    assert graph.cycles == ((1,),)
    assert graph.node(1).relation is StackRelation.CYCLE


def test_two_node_cycle_detected():
    one = snapshot(
        number=1,
        base_ref="feature/two",
        head_ref="feature/one",
        head_sha=SHA_B,
    )
    two = snapshot(
        number=2,
        base_ref="feature/one",
        head_ref="feature/two",
        head_sha=SHA_C,
    )
    graph = build_stack_graph((one, two), default_branch="main")
    assert graph.cycles == ((1, 2),)
    assert graph.node(1).relation is StackRelation.CYCLE
    assert graph.node(2).relation is StackRelation.CYCLE


def test_three_node_cycle_normalizes_to_smallest_number():
    one = snapshot(
        number=5,
        base_ref="feature/c",
        head_ref="feature/a",
        head_sha=SHA_B,
    )
    two = snapshot(
        number=9,
        base_ref="feature/a",
        head_ref="feature/b",
        head_sha=SHA_C,
    )
    three = snapshot(
        number=3,
        base_ref="feature/b",
        head_ref="feature/c",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((one, two, three), default_branch="main")
    assert graph.cycles == ((3, 9, 5),)


def test_multiple_independent_roots():
    graph = build_stack_graph(
        (
            _root(number=1, head_ref="feature/a", head_sha=SHA_B),
            _root(number=2, head_ref="feature/b", head_sha=SHA_C),
        ),
        default_branch="main",
    )
    assert graph.roots == (1, 2)


def test_children_are_sorted():
    root = _root()
    child_three = _child(
        number=3,
        head_ref="feature/three",
        head_sha=SHA_C,
    )
    child_two = _child(
        number=2,
        head_ref="feature/two",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, child_three, child_two), default_branch="main")
    assert graph.node(1).children == (2, 3)


def test_annotate_snapshot_copies_topology():
    root = _root()
    child = _child()
    graph = build_stack_graph((root, child), default_branch="main")
    annotated = annotate_snapshot(child, graph)
    assert annotated.stack_relation is StackRelation.CHILD
    assert annotated.parent_pr == 1
    assert annotated.identity == child.identity


def test_annotate_snapshot_rejects_absent_pr():
    graph = build_stack_graph((_root(),), default_branch="main")
    absent = _root(number=99, head_ref="feature/absent", head_sha=SHA_C)
    with pytest.raises(ValueError, match="absent"):
        annotate_snapshot(absent, graph)


def test_annotate_all():
    root = _root()
    child = _child()
    annotated = annotate_all((root, child), default_branch="main")
    by_number = {item.identity.number: item for item in annotated}
    assert by_number[1].stack_relation is StackRelation.ROOT
    assert by_number[2].stack_relation is StackRelation.CHILD


def test_descendants_returns_breadth_first_chain():
    root = _root()
    child = _child()
    grandchild = _child(
        number=3,
        parent_ref="feature/child",
        parent_sha=SHA_C,
        head_ref="feature/grandchild",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, child, grandchild), default_branch="main")
    assert descendants(graph, 1) == (2, 3)


def test_descendants_handles_branching():
    root = _root()
    child2 = _child(number=2, head_ref="feature/two", head_sha=SHA_C)
    child3 = _child(number=3, head_ref="feature/three", head_sha=SHA_D)
    graph = build_stack_graph((root, child2, child3), default_branch="main")
    assert descendants(graph, 1) == (2, 3)


def test_descendants_absent_number_empty():
    graph = build_stack_graph((_root(),), default_branch="main")
    assert descendants(graph, 99) == ()


def test_ancestors_returns_parent_to_root_order():
    root = _root()
    child = _child()
    grandchild = _child(
        number=3,
        parent_ref="feature/child",
        parent_sha=SHA_C,
        head_ref="feature/grandchild",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, child, grandchild), default_branch="main")
    assert ancestors(graph, 3) == (2, 1)


def test_ancestors_root_empty():
    graph = build_stack_graph((_root(),), default_branch="main")
    assert ancestors(graph, 1) == ()


def test_leaf_nodes_single_root():
    graph = build_stack_graph((_root(),), default_branch="main")
    assert leaf_nodes(graph) == (1,)


def test_leaf_nodes_returns_only_children_without_descendants():
    root = _root()
    child = _child()
    grandchild = _child(
        number=3,
        parent_ref="feature/child",
        parent_sha=SHA_C,
        head_ref="feature/grandchild",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, child, grandchild), default_branch="main")
    assert leaf_nodes(graph) == (3,)


def test_leaf_nodes_ignores_orphans_and_cycles():
    orphan = _child(parent_ref="missing")
    cycle = snapshot(
        number=3,
        base_ref="feature/cycle",
        head_ref="feature/cycle",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((orphan, cycle), default_branch="main")
    assert leaf_nodes(graph) == ()


def test_root_for_root():
    graph = build_stack_graph((_root(),), default_branch="main")
    assert root_for(graph, 1) == 1


def test_root_for_deep_child():
    root = _root()
    child = _child()
    grandchild = _child(
        number=3,
        parent_ref="feature/child",
        parent_sha=SHA_C,
        head_ref="feature/grandchild",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, child, grandchild), default_branch="main")
    assert root_for(graph, 3) == 1


def test_root_for_orphan_none():
    graph = build_stack_graph(
        (_child(parent_ref="missing"),),
        default_branch="main",
    )
    assert root_for(graph, 2) is None


def test_stack_groups_partition_valid_stacks():
    root1 = _root(number=1, head_ref="feature/a", head_sha=SHA_B)
    child1 = _child(
        number=2,
        parent_ref="feature/a",
        head_ref="feature/a-child",
        head_sha=SHA_C,
    )
    root2 = _root(number=3, head_ref="feature/b", head_sha=SHA_D)
    graph = build_stack_graph((root1, child1, root2), default_branch="main")
    groups = stack_groups(graph)
    assert groups[1] == (1, 2)
    assert groups[3] == (3,)


def test_landing_plan_selects_leaf_child():
    root = _root()
    child = _child()
    graph = build_stack_graph((root, child), default_branch="main")
    plan = landing_plan(graph, eligible=(2,), max_stack_merges=2)
    assert len(plan.steps) == 1
    assert plan.steps[0].pr_number == 2
    assert plan.steps[0].target_branch == "feature/root"
    assert plan.steps[0].parent_pr == 1


def test_landing_plan_does_not_select_root():
    graph = build_stack_graph((_root(),), default_branch="main")
    plan = landing_plan(graph, eligible=(1,), max_stack_merges=2)
    assert plan.steps == ()


def test_landing_plan_does_not_select_non_leaf_child():
    root = _root()
    child = _child()
    grandchild = _child(
        number=3,
        parent_ref="feature/child",
        parent_sha=SHA_C,
        head_ref="feature/grandchild",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, child, grandchild), default_branch="main")
    plan = landing_plan(graph, eligible=(2,), max_stack_merges=2)
    assert plan.steps == ()


def test_landing_plan_selects_deepest_leaf():
    root = _root()
    child = _child()
    grandchild = _child(
        number=3,
        parent_ref="feature/child",
        parent_sha=SHA_C,
        head_ref="feature/grandchild",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, child, grandchild), default_branch="main")
    plan = landing_plan(graph, eligible=(2, 3), max_stack_merges=2)
    assert [step.pr_number for step in plan.steps] == [3]


def test_landing_plan_emits_at_most_one_step_per_root():
    root = _root()
    child2 = _child(number=2, head_ref="feature/two", head_sha=SHA_C)
    child3 = _child(number=3, head_ref="feature/three", head_sha=SHA_D)
    graph = build_stack_graph((root, child2, child3), default_branch="main")
    plan = landing_plan(graph, eligible=(2, 3), max_stack_merges=2)
    assert len(plan.steps) == 1


def test_landing_plan_can_select_one_leaf_from_each_root():
    root1 = _root(number=1, head_ref="feature/a", head_sha=SHA_B)
    child1 = _child(
        number=2,
        parent_ref="feature/a",
        head_ref="feature/a-child",
        head_sha=SHA_C,
    )
    root2 = _root(number=3, head_ref="feature/b", head_sha=SHA_D)
    child2 = _child(
        number=4,
        parent_ref="feature/b",
        parent_sha=SHA_D,
        head_ref="feature/b-child",
        head_sha="e" * 40,
    )
    graph = build_stack_graph((root1, child1, root2, child2), default_branch="main")
    plan = landing_plan(graph, eligible=(2, 4), max_stack_merges=2)
    assert {step.pr_number for step in plan.steps} == {2, 4}


def test_landing_plan_respects_max_stack_merges():
    root1 = _root(number=1, head_ref="feature/a", head_sha=SHA_B)
    child1 = _child(
        number=2,
        parent_ref="feature/a",
        head_ref="feature/a-child",
        head_sha=SHA_C,
    )
    root2 = _root(number=3, head_ref="feature/b", head_sha=SHA_D)
    child2 = _child(
        number=4,
        parent_ref="feature/b",
        parent_sha=SHA_D,
        head_ref="feature/b-child",
        head_sha="e" * 40,
    )
    graph = build_stack_graph((root1, child1, root2, child2), default_branch="main")
    plan = landing_plan(graph, eligible=(2, 4), max_stack_merges=1)
    assert len(plan.steps) == 1


@pytest.mark.parametrize("value", [0, -1])
def test_landing_plan_rejects_invalid_merge_budget(value):
    graph = build_stack_graph((_root(),), default_branch="main")
    with pytest.raises(ValueError, match="positive"):
        landing_plan(graph, eligible=(), max_stack_merges=value)


def test_landing_plan_blocks_orphan():
    orphan = _child(parent_ref="missing")
    graph = build_stack_graph((orphan,), default_branch="main")
    plan = landing_plan(graph, eligible=(2,), max_stack_merges=1)
    assert plan.steps == ()
    assert 2 in plan.blocked


def test_landing_plan_blocks_cycle_members():
    one = snapshot(
        number=1,
        base_ref="feature/two",
        head_ref="feature/one",
        head_sha=SHA_B,
    )
    two = snapshot(
        number=2,
        base_ref="feature/one",
        head_ref="feature/two",
        head_sha=SHA_C,
    )
    graph = build_stack_graph((one, two), default_branch="main")
    plan = landing_plan(graph, eligible=(1, 2), max_stack_merges=2)
    assert plan.steps == ()
    assert set(plan.blocked) == {1, 2}


def test_landing_plan_blocks_duplicate_head_ambiguity():
    root = _root(number=1, head_ref="feature/shared", head_sha=SHA_B)
    duplicate = _root(number=2, head_ref="feature/shared", head_sha=SHA_C)
    child = _child(
        number=3,
        parent_ref="feature/shared",
        head_ref="feature/child",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((root, duplicate, child), default_branch="main")
    plan = landing_plan(graph, eligible=(3,), max_stack_merges=1)
    assert plan.steps == ()
    assert 3 in plan.blocked


def test_validate_graph_clean_graph_empty_findings():
    graph = build_stack_graph((_root(), _child()), default_branch="main")
    assert validate_graph(graph) == ()


def test_validate_graph_reports_orphan():
    graph = build_stack_graph(
        (_child(parent_ref="missing"),),
        default_branch="main",
    )
    findings = validate_graph(graph)
    assert any(item.startswith("orphans:") for item in findings)


def test_validate_graph_reports_cycle():
    item = snapshot(
        number=1,
        base_ref="feature/self",
        head_ref="feature/self",
    )
    graph = build_stack_graph((item,), default_branch="main")
    findings = validate_graph(graph)
    assert any(item.startswith("cycle:") for item in findings)


def test_validate_graph_reports_duplicate_heads():
    graph = build_stack_graph(
        (
            _root(number=1, head_ref="feature/shared"),
            _root(number=2, head_ref="feature/shared", head_sha=SHA_C),
        ),
        default_branch="main",
    )
    findings = validate_graph(graph)
    assert any(item.startswith("duplicate_heads:") for item in findings)


def test_graph_by_number_is_complete():
    graph = build_stack_graph((_root(), _child()), default_branch="main")
    assert set(graph.by_number()) == {1, 2}


def test_graph_node_absent_returns_none():
    graph = build_stack_graph((_root(),), default_branch="main")
    assert graph.node(999) is None


def test_empty_inventory_builds_empty_graph():
    graph = build_stack_graph((), default_branch="main")
    assert graph.nodes == ()
    assert graph.roots == ()
    assert graph.cycles == ()
    assert graph.orphans == ()


def test_identity_objects_can_build_graph_directly():
    root = identity(
        number=1,
        base_ref="main",
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = identity(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    graph = build_stack_graph((root, child), default_branch="main")
    assert graph.node(2).parent_pr == 1


def test_invalid_input_type_rejected():
    with pytest.raises(TypeError, match="CandidateSnapshot"):
        build_stack_graph((object(),), default_branch="main")


def test_landing_step_reason_requires_fresh_revalidation_semantics():
    graph = build_stack_graph((_root(), _child()), default_branch="main")
    plan = landing_plan(graph, eligible=(2,), max_stack_merges=1)
    assert "revalidation" in plan.steps[0].reason


def test_root_list_excludes_orphan():
    graph = build_stack_graph(
        (
            _root(),
            _child(number=9, parent_ref="missing", head_ref="feature/orphan"),
        ),
        default_branch="main",
    )
    assert graph.roots == (1,)


def test_orphan_depth_is_negative():
    graph = build_stack_graph(
        (_child(parent_ref="missing"),),
        default_branch="main",
    )
    assert graph.node(2).depth == -1


def test_cycle_depth_is_negative():
    item = snapshot(
        number=1,
        base_ref="feature/self",
        head_ref="feature/self",
    )
    graph = build_stack_graph((item,), default_branch="main")
    assert graph.node(1).depth == -1


def test_stack_group_orders_parent_before_child():
    graph = build_stack_graph((_root(), _child()), default_branch="main")
    assert stack_groups(graph)[1] == (1, 2)


def test_stack_group_orders_deep_chain_by_depth():
    root = _root()
    child = _child()
    grandchild = _child(
        number=3,
        parent_ref="feature/child",
        parent_sha=SHA_C,
        head_ref="feature/grandchild",
        head_sha=SHA_D,
    )
    graph = build_stack_graph((grandchild, child, root), default_branch="main")
    assert stack_groups(graph)[1] == (1, 2, 3)


def test_descendants_does_not_duplicate_shared_walk():
    root = _root()
    child2 = _child(number=2, head_ref="feature/two", head_sha=SHA_C)
    child3 = _child(number=3, head_ref="feature/three", head_sha=SHA_D)
    graph = build_stack_graph((root, child2, child3), default_branch="main")
    assert len(descendants(graph, 1)) == 2


def test_ancestors_cycle_does_not_loop_forever():
    one = snapshot(
        number=1,
        base_ref="feature/two",
        head_ref="feature/one",
        head_sha=SHA_B,
    )
    two = snapshot(
        number=2,
        base_ref="feature/one",
        head_ref="feature/two",
        head_sha=SHA_C,
    )
    graph = build_stack_graph((one, two), default_branch="main")
    chain = ancestors(graph, 1)
    assert len(chain) <= 2
