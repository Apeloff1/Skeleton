import pytest

from core.world_graph import PatchOp, WorldEdge, WorldGraph, WorldNode, WorldPatch
from core.world_graph_projection import project_world_graph


def graph() -> WorldGraph:
    return WorldGraph(
        revision=7,
        nodes=(
            WorldNode(node_id="root", kind="scene", name="Root"),
            WorldNode(
                node_id="player",
                kind="actor",
                name="Player",
                parent_id="root",
                properties={"health": 100},
            ),
        ),
        edges=(
            WorldEdge(
                edge_id="spawn",
                source_id="root",
                target_id="player",
                kind="spawns",
            ),
        ),
    )


def test_projection_matches_frontend_cockpit_state_contract_without_graph_contents():
    source = graph()
    projection = project_world_graph(
        source,
        project_id="projects/demo-1",
        dirty=True,
        source="jeeves-worldgraph",
    )

    assert projection.cockpit_state() == {
        "projectId": "projects/demo-1",
        "revision": 7,
        "semanticHash": source.semantic_hash(),
        "dirty": True,
        "source": "jeeves-worldgraph",
    }
    diagnostics = projection.as_dict()
    assert diagnostics["nodeCount"] == 2
    assert diagnostics["edgeCount"] == 1
    assert diagnostics["writable"] is False
    assert "nodes" not in diagnostics
    assert "edges" not in diagnostics
    assert "patch" not in diagnostics


def test_projection_observes_new_revision_and_hash_after_canonical_patch():
    source = graph()
    before = project_world_graph(source)
    source.apply(
        WorldPatch(
            patch_id="rename-player",
            base_revision=source.revision,
            expected_semantic_hash=source.semantic_hash(),
            operations=(
                PatchOp(
                    op="set_name",
                    target="player",
                    payload={"name": "Hero"},
                    expected_revision=1,
                ),
            ),
        )
    )
    after = project_world_graph(source)

    assert after.revision == before.revision + 1
    assert after.semantic_hash != before.semantic_hash
    assert after.node_count == before.node_count
    assert after.edge_count == before.edge_count


def test_projection_rejects_invalid_metadata_and_non_worldgraph_inputs():
    source = graph()
    for invalid in ("", " spaces ", "https://evil.example/x", "a" * 257):
        with pytest.raises(ValueError, match="project_id"):
            project_world_graph(source, project_id=invalid)

    with pytest.raises(ValueError, match="source"):
        project_world_graph(source, source="")
    with pytest.raises(TypeError, match="dirty"):
        project_world_graph(source, dirty=1)
    with pytest.raises(TypeError, match="WorldGraph"):
        project_world_graph(object())
