"""B020 natural-language iterative repair: bounded patch, preview, checks, rollback."""

from __future__ import annotations

import pytest

from skeleton.forge.creator.design_graph import build_design_graph
from skeleton.forge.creator.generated_history import (
    create_generated_history,
    current_generated_snapshot,
)
from skeleton.forge.creator.nl_repair import (
    MAX_TOUCHED,
    NaturalLanguageRepairError,
    accept_repair,
    parse_repair_request,
    propose_repair,
    rollback_repair,
)


def _graph(extra_nodes=()):
    nodes = [
        {"id": "mech.dash", "kind": "mechanic", "label": "Dash", "attributes": {"cooldown_s": 4, "enabled": True}},
        {"id": "mech.jump", "kind": "mechanic", "label": "Jump", "attributes": {"height_m": 2.0}},
        {"id": "scene.caves", "kind": "scene", "label": "Crystal Caves", "attributes": {"music": "drip"}},
        {"id": "asset.bat", "kind": "asset", "label": "Bat", "attributes": {}},
        {"id": "asset.bat2", "kind": "asset", "label": "bat", "attributes": {}},
        *extra_nodes,
    ]
    edges = [
        {"id": "e1", "kind": "contains", "source": "scene.caves", "target": "asset.bat", "attributes": {}},
        {"id": "e2", "kind": "depends_on", "source": "mech.dash", "target": "mech.jump", "attributes": {}},
    ]
    return build_design_graph(project_id="proj.demo", nodes=nodes, edges=edges)


def _history():
    return create_generated_history(_graph())


def _reason(exc_info):
    return exc_info.value.context["reason"]


def test_parses_multi_clause_request_into_bounded_resolved_ops():
    ops = parse_repair_request(
        _graph(),
        "Please lower the cooldown_s of dash by 50%; then rename the jump to Leap. also connect Crystal Caves to mech.jump as references",
    )
    assert [(o.op, o.node_id) for o in ops] == [
        ("adjust", "mech.dash"), ("rename", "mech.jump"), ("connect", "scene.caves"),
    ]
    assert ops[0].value == 2
    assert ops[1].value == "Leap"
    assert ops[2].target_id == "mech.jump" and ops[2].edge_kind == "references"


def test_literal_values_and_label_field():
    ops = parse_repair_request(_graph(), "set enabled of Dash to off; set name of Jump to Hop; set music of crystal caves to 'echo'")
    assert ops[0].value is False
    assert ops[1].op == "rename" and ops[1].value == "Hop"
    assert ops[2].value == "echo"


@pytest.mark.parametrize("request_text, reason", [
    ("", "empty"),
    ("make it more fun", "unparsed"),
    ("remove Dragon", "unknown_entity"),
    ("remove Bat", "ambiguous_entity"),
    ("increase height_m of Crystal Caves by 2", "type_mismatch"),
    ("set id of Dash to x", "forbidden_field"),
    ("connect Dash to Jump as hugs", "unknown_edge_kind"),
    ("; ".join(["rename Dash to D"] * 9), "bound"),
])
def test_rejects_rather_than_guesses(request_text, reason):
    with pytest.raises(NaturalLanguageRepairError) as exc:
        parse_repair_request(_graph(), request_text)
    assert _reason(exc) == reason


def test_proposal_previews_semantic_diff_without_touching_history():
    history = _history()
    before = current_generated_snapshot(history)
    proposal = propose_repair(history, "increase height_m of Jump by 1.5")
    assert proposal.ok
    assert proposal.preview.node_map()["mech.jump"].attribute_map()["height_m"] == 3.5
    assert proposal.summary and any("Jump" in line for line in proposal.summary)
    assert current_generated_snapshot(history).digest == before.digest
    assert proposal.to_dict()["ok"] is True


def test_remove_cascades_edges_and_counts_touched():
    proposal = propose_repair(_history(), "delete mech.jump")
    assert "mech.jump" not in proposal.preview.node_map()
    assert "e2" not in proposal.preview.edge_map()
    assert proposal.touched_count == 2


def test_failing_checks_block_accept_and_crashing_check_fails():
    def no_dash(graph):
        return ["dash must stay"] if "mech.dash" not in graph.node_map() else []

    def boom(graph):
        raise RuntimeError("bad")

    history = _history()
    proposal = propose_repair(history, "remove Dash", checks=[("keeps_dash", no_dash), ("boom", boom)])
    assert not proposal.ok
    assert [c.passed for c in proposal.checks] == [True, False, False]
    with pytest.raises(NaturalLanguageRepairError) as exc:
        accept_repair(history, proposal, checks=[("keeps_dash", no_dash), ("boom", boom)])
    assert _reason(exc) == "checks_failed"


def test_accept_then_rollback_restores_exact_state():
    history = _history()
    original = current_generated_snapshot(history)
    proposal = propose_repair(history, "disconnect Dash from Jump\nrename Crystal Caves to Deep Caves")
    history, applied, transition = accept_repair(history, proposal)
    assert transition.label.startswith("repair: ")
    assert current_generated_snapshot(history).digest == applied.digest
    assert applied.node_map()["scene.caves"].label == "Deep Caves"
    history, restored, _ = rollback_repair(history)
    assert restored.digest == original.digest
    with pytest.raises(Exception):
        rollback_repair(history)


def test_stale_and_forged_proposals_are_refused():
    history = _history()
    first = propose_repair(history, "rename Dash to Blink")
    second = propose_repair(history, "rename Jump to Hop")
    history, _, _ = accept_repair(history, first)
    with pytest.raises(NaturalLanguageRepairError) as exc:
        accept_repair(history, second)
    assert _reason(exc) == "stale"

    fresh = _history()
    proposal = propose_repair(fresh, "rename Dash to Blink")
    forged = type(proposal)(**{**{f: getattr(proposal, f) for f in proposal.__slots__}, "digest": "0" * 64})
    with pytest.raises(NaturalLanguageRepairError) as exc:
        accept_repair(fresh, forged)
    assert _reason(exc) == "digest_mismatch"


def test_no_change_and_touch_bound():
    with pytest.raises(NaturalLanguageRepairError) as exc:
        propose_repair(_history(), "rename Dash to Dash")
    assert _reason(exc) == "no_change"

    hub_edges = [
        {"id": f"n.leaf{i}", "kind": "content", "label": f"Leaf {i}", "attributes": {}}
        for i in range(MAX_TOUCHED + 2)
    ]
    nodes = [{"id": "n.hub", "kind": "system", "label": "Hub", "attributes": {}}, *hub_edges]
    edges = [{"id": f"h{i}", "kind": "contains", "source": "n.hub", "target": f"n.leaf{i}", "attributes": {}}
             for i in range(MAX_TOUCHED + 2)]
    graph = build_design_graph(project_id="proj.demo", nodes=nodes, edges=edges)
    with pytest.raises(NaturalLanguageRepairError) as exc:
        propose_repair(create_generated_history(graph), "remove Hub")
    assert _reason(exc) == "bound"


def test_legacy_shim_reexports():
    import skeleton.creator.nl_repair as legacy
    import skeleton.forge.creator.nl_repair as canonical
    assert legacy.propose_repair is canonical.propose_repair
