from __future__ import annotations

import copy

import pytest

from skeleton.automation import traceability as compatibility
from skeleton.contracts import traceability as canonical
from skeleton.contracts.traceability import (
    EdgeKind,
    GapKind,
    NodeKind,
    TraceEdge,
    TraceError,
    TraceNode,
    TraceabilityMatrix,
    TraversalDirection,
)


def matrix() -> TraceabilityMatrix:
    nodes = (
        TraceNode("REQ.1", NodeKind.REQUIREMENT, "masterplan:VOL-112#R1"),
        TraceNode("IMPL.1", NodeKind.IMPLEMENTATION, "skeleton/feature.py"),
        TraceNode("TEST.1", NodeKind.TEST, "skeleton/testing/test_feature.py"),
        TraceNode("EVID.1", NodeKind.EVIDENCE, "receipt:feature:1"),
    )
    edges = (
        TraceEdge("IMPL.1", "REQ.1", EdgeKind.IMPLEMENTS),
        TraceEdge("TEST.1", "IMPL.1", EdgeKind.VERIFIES),
        TraceEdge("EVID.1", "TEST.1", EdgeKind.EVIDENCES),
    )
    return TraceabilityMatrix(nodes, edges)


def test_automation_surface_has_no_parallel_authority() -> None:
    assert compatibility.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(compatibility, name) is getattr(canonical, name)


def test_bidirectional_impact_from_requirement_reaches_evidence() -> None:
    assert matrix().impact("REQ.1") == (
        "EVID.1",
        "IMPL.1",
        "REQ.1",
        "TEST.1",
    )


def test_changed_implementation_reaches_requirement_and_verification() -> None:
    assert set(matrix().impact("IMPL.1")) == {
        "REQ.1",
        "IMPL.1",
        "TEST.1",
        "EVID.1",
    }


def test_directional_lineage_queries_are_explicit() -> None:
    subject = matrix()
    assert subject.provenance("EVID.1") == (
        "EVID.1",
        "IMPL.1",
        "REQ.1",
        "TEST.1",
    )
    assert subject.dependents("REQ.1") == (
        "EVID.1",
        "IMPL.1",
        "REQ.1",
        "TEST.1",
    )
    assert subject.provenance("REQ.1") == ("REQ.1",)
    assert subject.dependents("EVID.1") == ("EVID.1",)


def test_traverse_can_exclude_origin() -> None:
    subject = matrix()
    assert subject.traverse(
        "IMPL.1",
        direction=TraversalDirection.FORWARD,
        include_start=False,
    ) == ("REQ.1",)


def test_requirement_and_evidence_projection() -> None:
    subject = matrix()
    assert subject.requirements_for("EVID.1") == ("REQ.1",)
    assert subject.evidence_for("REQ.1") == ("EVID.1",)


def test_complete_chain_has_no_gaps() -> None:
    report = matrix().report()
    assert report.complete is True
    assert report.gaps == ()
    assert len(report.digest) == 64


def test_orphan_requirement_reported() -> None:
    subject = TraceabilityMatrix(
        (TraceNode("REQ.1", NodeKind.REQUIREMENT, "plan:1"),),
        (),
    )
    assert subject.orphan_requirements() == ("REQ.1",)
    assert [(gap.kind, gap.node_id) for gap in subject.gaps()] == [
        (GapKind.REQUIREMENT_WITHOUT_IMPLEMENTATION, "REQ.1")
    ]


def test_all_missing_link_classes_are_reported() -> None:
    subject = TraceabilityMatrix(
        (
            TraceNode("REQ.1", NodeKind.REQUIREMENT, "plan:1"),
            TraceNode("IMPL.1", NodeKind.IMPLEMENTATION, "impl.py"),
            TraceNode("TEST.1", NodeKind.TEST, "test_impl.py"),
            TraceNode("EVID.1", NodeKind.EVIDENCE, "receipt:1"),
        ),
        (),
    )
    assert {(gap.kind, gap.node_id) for gap in subject.gaps()} == {
        (GapKind.REQUIREMENT_WITHOUT_IMPLEMENTATION, "REQ.1"),
        (GapKind.IMPLEMENTATION_WITHOUT_REQUIREMENT, "IMPL.1"),
        (GapKind.IMPLEMENTATION_WITHOUT_TEST, "IMPL.1"),
        (GapKind.TEST_WITHOUT_IMPLEMENTATION, "TEST.1"),
        (GapKind.TEST_WITHOUT_EVIDENCE, "TEST.1"),
        (GapKind.EVIDENCE_WITHOUT_TEST, "EVID.1"),
    }


def test_dangling_edge_rejected() -> None:
    with pytest.raises(TraceError, match="dangling"):
        TraceabilityMatrix(
            (TraceNode("REQ.1", NodeKind.REQUIREMENT, "plan:1"),),
            (TraceEdge("IMPL.9", "REQ.1", EdgeKind.IMPLEMENTS),),
        )


@pytest.mark.parametrize(
    ("source_kind", "target_kind", "edge_kind"),
    [
        (NodeKind.TEST, NodeKind.REQUIREMENT, EdgeKind.IMPLEMENTS),
        (NodeKind.EVIDENCE, NodeKind.IMPLEMENTATION, EdgeKind.VERIFIES),
        (NodeKind.IMPLEMENTATION, NodeKind.TEST, EdgeKind.EVIDENCES),
    ],
)
def test_contradictory_typed_edges_rejected(
    source_kind: NodeKind,
    target_kind: NodeKind,
    edge_kind: EdgeKind,
) -> None:
    nodes = (
        TraceNode("NODE.A", source_kind, "source"),
        TraceNode("NODE.B", target_kind, "target"),
    )
    with pytest.raises(TraceError, match="contradictory"):
        TraceabilityMatrix(
            nodes,
            (TraceEdge("NODE.A", "NODE.B", edge_kind),),
        )


def test_cross_kind_dependency_rejected() -> None:
    nodes = (
        TraceNode("REQ.1", NodeKind.REQUIREMENT, "plan"),
        TraceNode("IMPL.1", NodeKind.IMPLEMENTATION, "impl.py"),
    )
    with pytest.raises(TraceError, match="same-kind"):
        TraceabilityMatrix(
            nodes,
            (TraceEdge("IMPL.1", "REQ.1", EdgeKind.DEPENDS_ON),),
        )


def test_dependency_cycle_rejected() -> None:
    nodes = (
        TraceNode("REQ.A", NodeKind.REQUIREMENT, "plan:a"),
        TraceNode("REQ.B", NodeKind.REQUIREMENT, "plan:b"),
        TraceNode("REQ.C", NodeKind.REQUIREMENT, "plan:c"),
    )
    edges = (
        TraceEdge("REQ.A", "REQ.B", EdgeKind.DEPENDS_ON),
        TraceEdge("REQ.B", "REQ.C", EdgeKind.DEPENDS_ON),
        TraceEdge("REQ.C", "REQ.A", EdgeKind.DEPENDS_ON),
    )
    with pytest.raises(TraceError, match="dependency cycle"):
        TraceabilityMatrix(nodes, edges)


def test_acyclic_same_kind_dependencies_are_supported() -> None:
    nodes = (
        TraceNode("REQ.A", NodeKind.REQUIREMENT, "plan:a"),
        TraceNode("REQ.B", NodeKind.REQUIREMENT, "plan:b"),
        TraceNode("REQ.C", NodeKind.REQUIREMENT, "plan:c"),
    )
    subject = TraceabilityMatrix(
        nodes,
        (
            TraceEdge("REQ.C", "REQ.B", EdgeKind.DEPENDS_ON),
            TraceEdge("REQ.B", "REQ.A", EdgeKind.DEPENDS_ON),
        ),
    )
    assert subject.provenance("REQ.C") == ("REQ.A", "REQ.B", "REQ.C")


def test_self_edge_rejected() -> None:
    with pytest.raises(TraceError, match="self"):
        TraceEdge("REQ.1", "REQ.1", EdgeKind.DEPENDS_ON)


def test_duplicate_node_rejected_even_for_generator_input() -> None:
    nodes = (
        TraceNode("REQ.1", NodeKind.REQUIREMENT, "plan:1"),
        TraceNode("REQ.1", NodeKind.REQUIREMENT, "plan:2"),
    )
    with pytest.raises(TraceError, match="duplicate trace node"):
        TraceabilityMatrix((node for node in nodes), ())


def test_duplicate_edge_rejected() -> None:
    nodes = (
        TraceNode("REQ.1", NodeKind.REQUIREMENT, "plan"),
        TraceNode("IMPL.1", NodeKind.IMPLEMENTATION, "impl.py"),
    )
    edge = TraceEdge("IMPL.1", "REQ.1", EdgeKind.IMPLEMENTS)
    with pytest.raises(TraceError, match="duplicate trace edge"):
        TraceabilityMatrix(nodes, (edge, edge))


def test_locator_is_canonical_and_control_character_free() -> None:
    with pytest.raises(TraceError, match="canonical"):
        TraceNode("REQ.1", NodeKind.REQUIREMENT, " padded ")
    with pytest.raises(TraceError, match="control"):
        TraceNode("REQ.1", NodeKind.REQUIREMENT, "bad\nlocator")


def test_stable_identifiers_fail_closed() -> None:
    for bad in ("x", "lower.case", "HAS SPACE", "", "A" * 129):
        with pytest.raises(TraceError, match="stable identifier"):
            TraceNode(bad, NodeKind.REQUIREMENT, "plan")


def test_order_independent_matrix_identity() -> None:
    subject = matrix()
    reversed_matrix = TraceabilityMatrix(
        reversed(tuple(subject.nodes.values())),
        reversed(subject.edges),
    )
    assert reversed_matrix.digest == subject.digest
    assert reversed_matrix.to_dict() == subject.to_dict()


def test_node_or_edge_change_changes_matrix_identity() -> None:
    original = matrix()
    changed_node = TraceabilityMatrix(
        (
            TraceNode("REQ.1", NodeKind.REQUIREMENT, "masterplan:VOL-112#R2"),
            TraceNode("IMPL.1", NodeKind.IMPLEMENTATION, "skeleton/feature.py"),
            TraceNode("TEST.1", NodeKind.TEST, "skeleton/testing/test_feature.py"),
            TraceNode("EVID.1", NodeKind.EVIDENCE, "receipt:feature:1"),
        ),
        original.edges,
    )
    assert changed_node.digest != original.digest

    changed_edges = TraceabilityMatrix(
        tuple(original.nodes.values()),
        (
            TraceEdge("IMPL.1", "REQ.1", EdgeKind.IMPLEMENTS),
            TraceEdge("TEST.1", "IMPL.1", EdgeKind.VERIFIES),
        ),
    )
    assert changed_edges.digest != original.digest


def test_round_trip_preserves_exact_identity() -> None:
    original = matrix()
    restored = TraceabilityMatrix.from_dict(original.to_dict())
    assert restored.digest == original.digest
    assert restored.to_dict() == original.to_dict()


def test_serialized_digest_tampering_rejected() -> None:
    payload = matrix().to_dict()
    payload["digest"] = "0" * 64
    with pytest.raises(TraceError, match="digest mismatch"):
        TraceabilityMatrix.from_dict(payload)


def test_serialized_node_tampering_rejected_even_with_original_digest() -> None:
    payload = copy.deepcopy(matrix().to_dict())
    payload["nodes"][0]["locator"] = "receipt:tampered"
    with pytest.raises(TraceError, match="digest mismatch"):
        TraceabilityMatrix.from_dict(payload)


def test_unknown_schema_rejected() -> None:
    payload = matrix().to_dict()
    payload["schema"] = "skeleton.contracts.traceability.v999"
    with pytest.raises(TraceError, match="unsupported"):
        TraceabilityMatrix.from_dict(payload)


def test_unknown_payload_fields_rejected() -> None:
    payload = matrix().to_dict()
    payload["surprise"] = True
    with pytest.raises(TraceError, match="unknown or missing"):
        TraceabilityMatrix.from_dict(payload)


def test_unknown_node_and_edge_kinds_rejected() -> None:
    with pytest.raises(TraceError, match="unknown trace node kind"):
        TraceNode.from_dict(
            {"node_id": "REQ.1", "kind": "magic", "locator": "plan"}
        )
    with pytest.raises(TraceError, match="unknown trace edge kind"):
        TraceEdge.from_dict(
            {"source_id": "REQ.A", "target_id": "REQ.B", "kind": "magic"}
        )


def test_edges_from_and_edges_to_can_filter_by_kind() -> None:
    subject = matrix()
    assert subject.edges_from("TEST.1", kind=EdgeKind.VERIFIES) == (
        TraceEdge("TEST.1", "IMPL.1", EdgeKind.VERIFIES),
    )
    assert subject.edges_to("TEST.1", kind=EdgeKind.EVIDENCES) == (
        TraceEdge("EVID.1", "TEST.1", EdgeKind.EVIDENCES),
    )
    assert subject.edges_from("TEST.1", kind=EdgeKind.EVIDENCES) == ()


def test_unknown_query_node_rejected() -> None:
    with pytest.raises(TraceError, match="unknown trace node"):
        matrix().impact("REQ.404")


def test_query_type_mismatch_rejected() -> None:
    with pytest.raises(TypeError, match="TraversalDirection"):
        matrix().traverse("REQ.1", direction="both")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="EdgeKind"):
        matrix().edges_from("REQ.1", kind="implements")  # type: ignore[arg-type]


def test_matrix_rejects_non_contract_objects() -> None:
    with pytest.raises(TypeError, match="TraceNode"):
        TraceabilityMatrix(("REQ.1",), ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TraceEdge"):
        TraceabilityMatrix(
            (TraceNode("REQ.1", NodeKind.REQUIREMENT, "plan"),),
            ("REQ.1",),  # type: ignore[arg-type]
        )

def test_requirement_projection_does_not_leak_across_dependency_edges() -> None:
    nodes = (
        TraceNode("REQ.A", NodeKind.REQUIREMENT, "plan:a"),
        TraceNode("REQ.B", NodeKind.REQUIREMENT, "plan:b"),
        TraceNode("IMPL.A", NodeKind.IMPLEMENTATION, "a.py"),
        TraceNode("TEST.A", NodeKind.TEST, "test_a.py"),
        TraceNode("EVID.A", NodeKind.EVIDENCE, "receipt:a"),
    )
    subject = TraceabilityMatrix(nodes, (
        TraceEdge("IMPL.A", "REQ.A", EdgeKind.IMPLEMENTS),
        TraceEdge("TEST.A", "IMPL.A", EdgeKind.VERIFIES),
        TraceEdge("EVID.A", "TEST.A", EdgeKind.EVIDENCES),
        TraceEdge("REQ.A", "REQ.B", EdgeKind.DEPENDS_ON),
    ))
    assert subject.requirements_for("EVID.A") == ("REQ.A",)
    assert subject.evidence_for("REQ.B") == ()
    assert "REQ.B" in subject.impact("EVID.A")


def test_graph_materialization_stops_at_safety_bound() -> None:
    consumed = 0

    def nodes():
        nonlocal consumed
        while True:
            consumed += 1
            yield TraceNode(f"REQ.{consumed}", NodeKind.REQUIREMENT, f"plan:{consumed}")

    with pytest.raises(TraceError, match="trace node count exceeds safety bound"):
        TraceabilityMatrix(nodes(), ())
    assert consumed == 10_001


def test_non_iterable_graph_inputs_fail_with_stable_type_errors() -> None:
    with pytest.raises(TypeError, match="nodes must be iterable"):
        TraceabilityMatrix(None, ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="edges must be iterable"):
        TraceabilityMatrix((), None)  # type: ignore[arg-type]
