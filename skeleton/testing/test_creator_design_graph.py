"""Regression tests for the persistent creator design graph (#807 B012)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.creator.design_graph import (
    DesignGraphEdge,
    DesignGraphError,
    DesignGraphNode,
    build_design_graph,
    design_graph_from_plan,
    parse_design_graph,
)
from skeleton.creator.intent_compiler import compile_intent


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "intent_compiler"
    / "harbor_heist_v1.json"
)


def _plan():
    return compile_intent(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _manual_graph():
    return build_design_graph(
        project_id="project_demo",
        revision=3,
        nodes=(
            DesignGraphNode("scene_harbor", "scene", "Harbor"),
            DesignGraphNode("mechanic_stealth", "mechanic", "Stealth"),
            DesignGraphNode("asset_boat", "asset", "Boat"),
            DesignGraphNode("narrative_escape", "narrative", "Escape"),
        ),
        edges=(
            DesignGraphEdge(
                "depends:mechanic_stealth:scene_harbor",
                "depends_on",
                "mechanic_stealth",
                "scene_harbor",
            ),
            DesignGraphEdge(
                "references:narrative_escape:asset_boat",
                "references",
                "narrative_escape",
                "asset_boat",
            ),
        ),
    )


def test_b011_plan_projects_to_queryable_typed_graph() -> None:
    plan = _plan()

    graph = design_graph_from_plan(plan)

    assert graph.project_id == plan.request_id
    assert graph.revision == plan.revision
    assert graph.source_plan_digest == plan.digest()
    assert graph.node_map()["n_world"].kind == "world"
    assert graph.node_map()["n_stealth"].kind == "mechanic"

    dependencies = graph.outgoing("n_stealth", kind="depends_on")
    assert tuple(edge.target for edge in dependencies) == ("n_world",)

    constraint_ids = {
        f"constraint:{row.constraint_id}" for row in plan.constraints
    }
    evidence_ids = {
        f"evidence:{row.validation_id}" for row in plan.validations
    }
    assert constraint_ids <= set(graph.node_map())
    assert evidence_ids <= set(graph.node_map())
    assert len(graph.nodes_of_kind("evidence")) == len(plan.validations)


def test_graph_round_trip_is_digest_bound_and_byte_stable() -> None:
    graph = design_graph_from_plan(_plan())

    parsed = parse_design_graph(graph.serialize())

    assert parsed == graph
    assert parsed.digest == graph.digest
    assert parsed.serialize() == graph.serialize()


def test_declaration_order_does_not_change_graph_identity() -> None:
    graph = _manual_graph()

    reversed_graph = build_design_graph(
        project_id=graph.project_id,
        revision=graph.revision,
        nodes=reversed(graph.nodes),
        edges=reversed(graph.edges),
    )

    assert reversed_graph == graph
    assert reversed_graph.digest == graph.digest
    assert reversed_graph.serialize() == graph.serialize()


def test_typed_queries_are_deterministic() -> None:
    graph = _manual_graph()

    assert tuple(node.node_id for node in graph.nodes_of_kind("asset")) == (
        "asset_boat",
    )
    assert tuple(
        edge.edge_id for edge in graph.incoming("scene_harbor", kind="depends_on")
    ) == ("depends:mechanic_stealth:scene_harbor",)
    assert tuple(
        node.node_id for node in graph.neighbors("mechanic_stealth")
    ) == ("scene_harbor",)

    with pytest.raises(DesignGraphError, match="unknown design graph node"):
        graph.outgoing("missing")


def test_unknown_endpoints_self_edges_and_duplicate_ids_fail_closed() -> None:
    nodes = (
        DesignGraphNode("scene_harbor", "scene", "Harbor"),
        DesignGraphNode("mechanic_stealth", "mechanic", "Stealth"),
    )

    with pytest.raises(DesignGraphError, match="unknown node"):
        build_design_graph(
            project_id="project_demo",
            nodes=nodes,
            edges=(
                DesignGraphEdge(
                    "references:mechanic_stealth:missing",
                    "references",
                    "mechanic_stealth",
                    "missing",
                ),
            ),
        )

    with pytest.raises(DesignGraphError, match="self edges"):
        build_design_graph(
            project_id="project_demo",
            nodes=nodes,
            edges=(
                DesignGraphEdge(
                    "references:scene_harbor:scene_harbor",
                    "references",
                    "scene_harbor",
                    "scene_harbor",
                ),
            ),
        )

    with pytest.raises(DesignGraphError, match="duplicate design graph node"):
        build_design_graph(
            project_id="project_demo",
            nodes=(nodes[0], nodes[0]),
            edges=(),
        )

    duplicate_edge = DesignGraphEdge(
        "references:mechanic_stealth:scene_harbor",
        "references",
        "mechanic_stealth",
        "scene_harbor",
    )
    with pytest.raises(DesignGraphError, match="duplicate design graph edge"):
        build_design_graph(
            project_id="project_demo",
            nodes=nodes,
            edges=(duplicate_edge, duplicate_edge),
        )


def test_unknown_kinds_and_non_scalar_attributes_fail_closed() -> None:
    with pytest.raises(DesignGraphError, match="node kind"):
        build_design_graph(
            project_id="project_demo",
            nodes=(DesignGraphNode("x", "executable", "Nope"),),
            edges=(),
        )

    with pytest.raises(DesignGraphError, match="JSON scalar"):
        build_design_graph(
            project_id="project_demo",
            nodes=(
                DesignGraphNode(
                    "scene_harbor",
                    "scene",
                    "Harbor",
                    attributes=(("payload", {"nested": "not allowed"}),),
                ),
            ),
            edges=(),
        )


def test_tampered_digest_fails_closed() -> None:
    graph = _manual_graph()
    payload = json.loads(graph.serialize())
    payload["nodes"][0]["label"] = "Tampered"

    with pytest.raises(DesignGraphError, match="digest mismatch"):
        parse_design_graph(payload)


def test_duplicate_json_keys_and_bad_version_fail_closed() -> None:
    graph = _manual_graph()
    serialized = graph.serialize()
    duplicate = serialized.replace(
        '"schema":"creator.design_graph.v1"',
        '"schema":"creator.design_graph.v1","schema":"creator.design_graph.v1"',
        1,
    )
    with pytest.raises(DesignGraphError, match="duplicate JSON key"):
        parse_design_graph(duplicate)

    payload = json.loads(serialized)
    payload["schema_version"] = 2
    with pytest.raises(DesignGraphError, match="version"):
        parse_design_graph(payload)


def test_boolean_revision_does_not_coerce_to_integer() -> None:
    with pytest.raises(DesignGraphError, match="revision must be an integer"):
        build_design_graph(
            project_id="project_demo",
            revision=True,  # type: ignore[arg-type]
            nodes=(DesignGraphNode("scene_harbor", "scene", "Harbor"),),
            edges=(),
        )
