import pytest

from core.world_graph import (
    PatchOp,
    PatchRejected,
    RevisionConflict,
    WorldGraph,
    WorldNode,
    WorldPatch,
)


def _graph():
    return WorldGraph(
        nodes=(
            WorldNode("world", "world", "World"),
            WorldNode("player", "actor", "Player", parent_id="world"),
        )
    )


def test_patch_is_atomic_when_late_operation_fails():
    graph = _graph()
    before = graph.snapshot()
    patch = WorldPatch(
        graph.revision,
        (
            PatchOp("set_property", "player", {"key": "hp", "value": 100}),
            PatchOp("move_node", "player", {"parent_id": "missing"}),
        ),
    )
    with pytest.raises(PatchRejected, match="missing parent"):
        graph.apply(patch)
    assert graph.snapshot() == before


def test_stale_revision_and_semantic_hash_fail_closed():
    graph = _graph()
    with pytest.raises(RevisionConflict, match="stale graph revision"):
        graph.apply(
            WorldPatch(
                graph.revision + 1,
                (PatchOp("set_name", "player", {"name": "Hero"}),),
            )
        )

    with pytest.raises(RevisionConflict, match="semantic hash"):
        graph.apply(
            WorldPatch(
                graph.revision,
                (PatchOp("set_name", "player", {"name": "Hero"}),),
                expected_semantic_hash="f" * 64,
            )
        )


def test_object_revision_precondition_detects_stale_edit():
    graph = _graph()
    graph.apply(
        WorldPatch(
            0,
            (PatchOp("set_name", "player", {"name": "Hero"}, expected_revision=1),),
        )
    )
    assert graph.get_node("player").revision == 2
    with pytest.raises(RevisionConflict, match="stale object revision"):
        graph.apply(
            WorldPatch(
                1,
                (PatchOp("set_property", "player", {"key": "hp", "value": 100}, expected_revision=1),),
            )
        )


def test_parent_cycle_is_rejected_without_partial_state():
    graph = _graph()
    before_hash = graph.semantic_hash()
    with pytest.raises(PatchRejected, match="cycle"):
        graph.apply(
            WorldPatch(
                graph.revision,
                (PatchOp("move_node", "world", {"parent_id": "player"}),),
            )
        )
    assert graph.semantic_hash() == before_hash
    assert graph.revision == 0


def test_node_component_property_edge_patch_and_rollback_restore_semantics():
    graph = _graph()
    baseline_hash = graph.semantic_hash()
    patch = WorldPatch(
        graph.revision,
        (
            PatchOp(
                "create_node",
                "door",
                {
                    "kind": "prop",
                    "name": "Door",
                    "parent_id": "world",
                    "properties": {"locked": True},
                },
            ),
            PatchOp(
                "set_component",
                "door",
                {"component": "transform", "value": {"x": 4, "y": 0, "z": 2}},
            ),
            PatchOp(
                "create_edge",
                "player-opens-door",
                {
                    "source_id": "player",
                    "target_id": "door",
                    "kind": "signal",
                    "properties": {"event": "interact"},
                },
            ),
            PatchOp("set_property", "player", {"key": "can_open_doors", "value": True}),
        ),
        author="jeeves",
        capability="world.patch",
        evidence_ids=("test:world-1",),
        expected_semantic_hash=baseline_hash,
    )
    result = graph.apply(patch)
    assert graph.revision == 1
    assert graph.get_node("door").components["transform"]["x"] == 4
    assert graph.get_edge("player-opens-door").kind == "signal"
    assert result.before_hash == baseline_hash
    assert result.after_hash == graph.semantic_hash()
    assert result.evidence_ids == ("test:world-1",)

    undo = graph.rollback(result)
    assert undo.from_revision == 1
    assert graph.revision == 2
    assert graph.semantic_hash() == baseline_hash
    assert graph.get_node("door") is None
    assert graph.get_edge("player-opens-door") is None
    assert "can_open_doors" not in graph.get_node("player").properties


def test_cascade_delete_requires_explicit_edge_deletion_and_is_reversible():
    graph = WorldGraph(
        nodes=(
            WorldNode("root", "world", "Root"),
            WorldNode("a", "actor", "A", parent_id="root"),
            WorldNode("b", "part", "B", parent_id="a"),
        )
    )
    graph.apply(
        WorldPatch(
            0,
            (
                PatchOp(
                    "create_edge",
                    "edge-1",
                    {"source_id": "root", "target_id": "b", "kind": "signal"},
                ),
            ),
        )
    )
    before = graph.semantic_hash()

    with pytest.raises(PatchRejected, match="delete_edges=true"):
        graph.apply(
            WorldPatch(
                1,
                (PatchOp("delete_node", "a", {"cascade": True}),),
            )
        )

    result = graph.apply(
        WorldPatch(
            1,
            (PatchOp("delete_node", "a", {"cascade": True, "delete_edges": True}),),
        )
    )
    assert graph.get_node("a") is None
    assert graph.get_node("b") is None
    assert graph.get_edge("edge-1") is None

    graph.rollback(result)
    assert graph.semantic_hash() == before
    assert graph.get_node("a").parent_id == "root"
    assert graph.get_node("b").parent_id == "a"
    assert graph.get_edge("edge-1").target_id == "b"


def test_delete_non_leaf_requires_explicit_cascade():
    graph = _graph()
    with pytest.raises(PatchRejected, match="cascade=true"):
        graph.apply(
            WorldPatch(
                graph.revision,
                (PatchOp("delete_node", "world"),),
            )
        )


def test_snapshot_round_trip_has_stable_semantic_identity():
    graph = _graph()
    graph.apply(
        WorldPatch(
            0,
            (
                PatchOp("set_property", "player", {"key": "inventory", "value": ["key", "map"]}),
                PatchOp("set_package_ref", "player", {"package_ref": "actors/player@2"}),
            ),
        )
    )
    snapshot = graph.snapshot()
    clone = WorldGraph.from_snapshot(snapshot)
    assert clone.snapshot() == snapshot
    assert clone.semantic_hash() == graph.semantic_hash()


def test_edge_endpoint_validation_is_atomic():
    graph = _graph()
    before = graph.snapshot()
    with pytest.raises(PatchRejected, match="endpoints"):
        graph.apply(
            WorldPatch(
                0,
                (
                    PatchOp(
                        "create_edge",
                        "bad",
                        {"source_id": "player", "target_id": "ghost", "kind": "signal"},
                    ),
                ),
            )
        )
    assert graph.snapshot() == before
