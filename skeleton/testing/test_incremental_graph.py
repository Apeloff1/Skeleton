"""Fail-closed tests for the content-addressed incremental build graph (#940)."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import hashlib
import inspect
import json

import pytest

from skeleton.build.incremental_graph import (
    FINGERPRINT_ALGORITHM,
    GRAPH_SCHEMA,
    MAX_EDGES,
    MAX_NODES,
    MAX_TRAVERSAL_VISITS,
    IncrementalGraphError,
    NodeSpec,
    build_incremental_graph,
)
from skeleton.build import incremental_graph as graph_mod


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _units(*rows: tuple[str, tuple[str, ...], dict[str, str] | None, int]) -> list[dict[str, object]]:
    specs = []
    for node_id, deps, inputs, cost in rows:
        specs.append(
            {
                "id": node_id,
                "dependencies": list(deps),
                "inputs": dict(inputs or {}),
                "cost": cost,
            }
        )
    return specs


def test_identical_inputs_are_deterministic_regardless_of_declaration_order() -> None:
    left = build_incremental_graph(
        _units(
            ("link", ("obj_b", "obj_a"), {"cmd": "ld"}, 3),
            ("obj_a", ("src_a",), {"cmd": "cc"}, 2),
            ("src_a", (), {"blob": "int a;"}, 1),
            ("obj_b", ("src_b",), {"cmd": "cc"}, 2),
            ("src_b", (), {"blob": "int b;"}, 1),
        )
    )
    right = build_incremental_graph(
        [
            NodeSpec("src_b", inputs={"blob": "int b;"}),
            NodeSpec("src_a", inputs={"blob": "int a;"}),
            NodeSpec("obj_b", inputs={"cmd": "cc"}, dependencies=("src_b",), cost=2),
            NodeSpec("obj_a", inputs={"cmd": "cc"}, dependencies=("src_a",), cost=2),
            NodeSpec("link", inputs={"cmd": "ld"}, dependencies=("obj_a", "obj_b"), cost=3),
        ]
    )

    assert left.fingerprint == right.fingerprint
    assert left.serialize() == right.serialize()
    assert json.loads(left.serialize())["algorithm"] == FINGERPRINT_ALGORITHM
    assert len(left.fingerprint) == 64
    assert all(len(node.fingerprint) == 64 for node in left.nodes)


def test_stable_serialization_is_canonical_json() -> None:
    graph = build_incremental_graph(
        [
            {"id": "leaf", "inputs": {"z": "2", "a": "1"}},
            {"id": "root", "dependencies": ["leaf"], "cost": 4},
        ]
    )
    encoded = graph.serialize()
    parsed = json.loads(encoded)
    assert encoded == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert parsed["schema"] == GRAPH_SCHEMA
    assert parsed["nodes"][0]["id"] == "leaf"
    assert parsed["nodes"][0]["inputs"] == [["a", _sha256_text("1")], ["z", _sha256_text("2")]]
    rebuilt = build_incremental_graph(
        [
            {"id": "root", "dependencies": ["leaf"], "cost": 4},
            {"id": "leaf", "inputs": {"a": "1", "z": "2"}},
        ]
    )
    assert rebuilt.serialize() == encoded


def test_cycle_detection_fails_closed_and_emits_no_graph() -> None:
    with pytest.raises(IncrementalGraphError) as exc:
        build_incremental_graph(
            [
                {"id": "a", "dependencies": ["b"]},
                {"id": "b", "dependencies": ["c"]},
                {"id": "c", "dependencies": ["a"]},
            ]
        )
    assert exc.value.code == "BUILD.INCREMENTAL_GRAPH"
    assert "cycle" in exc.value.message
    assert "a" in exc.value.context["cycle"]


def test_self_cycle_fails_closed() -> None:
    with pytest.raises(IncrementalGraphError, match="cycle"):
        build_incremental_graph([{"id": "loop", "dependencies": ["loop"]}])


def test_topological_order_is_dependencies_first_and_stable() -> None:
    graph = build_incremental_graph(
        [
            {"id": "z", "dependencies": ["m", "a"]},
            {"id": "m", "dependencies": ["a"]},
            {"id": "a"},
            {"id": "b"},
        ]
    )
    assert graph.topological_order.index("a") < graph.topological_order.index("m")
    assert graph.topological_order.index("m") < graph.topological_order.index("z")
    assert graph.topological_order.index("a") < graph.topological_order.index("z")
    # Ready-set is sorted, so independent roots appear in lexicographic order.
    assert graph.topological_order[:2] == ("a", "b")


def test_fanout_invalidates_every_dependent_and_not_unrelated_siblings() -> None:
    graph = build_incremental_graph(
        [
            {"id": "shared", "inputs": {"blob": "v1"}},
            {"id": "left", "dependencies": ["shared"]},
            {"id": "right", "dependencies": ["shared"]},
            {"id": "sink", "dependencies": ["left", "right"]},
            {"id": "other", "inputs": {"blob": "independent"}},
        ]
    )
    stale = graph.invalidate(["shared"])
    assert stale == frozenset({"shared", "left", "right", "sink"})
    assert "other" not in stale


def test_changed_inputs_invalidate_only_dependent_nodes() -> None:
    original = build_incremental_graph(
        [
            {"id": "src", "inputs": {"blob": "alpha"}},
            {"id": "mid", "dependencies": ["src"], "inputs": {"cmd": "cc"}},
            {"id": "out", "dependencies": ["mid"], "inputs": {"cmd": "ld"}},
            {"id": "untouched", "inputs": {"blob": "keep"}},
        ]
    )
    changed = build_incremental_graph(
        [
            {"id": "src", "inputs": {"blob": "beta"}},
            {"id": "mid", "dependencies": ["src"], "inputs": {"cmd": "cc"}},
            {"id": "out", "dependencies": ["mid"], "inputs": {"cmd": "ld"}},
            {"id": "untouched", "inputs": {"blob": "keep"}},
        ]
    )
    locally_changed = [
        node.node_id
        for node in original.nodes
        if node.local_fingerprint != changed.node_map()[node.node_id].local_fingerprint
    ]
    assert locally_changed == ["src"]
    stale = original.invalidate(locally_changed)
    assert stale == frozenset({"src", "mid", "out"})
    assert original.node_map()["untouched"].fingerprint == changed.node_map()["untouched"].fingerprint
    assert original.node_map()["mid"].fingerprint != changed.node_map()["mid"].fingerprint
    assert original.fingerprint != changed.fingerprint


def test_critical_path_uses_longest_cost_chain_and_is_stable() -> None:
    graph = build_incremental_graph(
        [
            {"id": "a", "cost": 1},
            {"id": "b", "cost": 10},
            {"id": "join", "dependencies": ["a", "b"], "cost": 2},
            {"id": "tail", "dependencies": ["join"], "cost": 3},
        ]
    )
    assert graph.critical_path.nodes == ("b", "join", "tail")
    assert graph.critical_path.cost == 15
    assert graph.critical_path.length == 3
    # Tie on total cost: lexicographically smallest sink, then smallest predecessor.
    tied = build_incremental_graph(
        [
            {"id": "x", "cost": 5},
            {"id": "y", "cost": 5},
        ]
    )
    assert tied.critical_path.nodes == ("x",)


def test_malformed_input_fails_closed() -> None:
    with pytest.raises(IncrementalGraphError, match="at least one node"):
        build_incremental_graph([])
    with pytest.raises(IncrementalGraphError, match="must be a sequence"):
        build_incremental_graph("not-a-graph")  # type: ignore[arg-type]
    with pytest.raises(IncrementalGraphError, match="unknown keys"):
        build_incremental_graph([{"id": "a", "shell": "rm -rf /"}])
    with pytest.raises(IncrementalGraphError, match="non-empty trimmed"):
        build_incremental_graph([{"id": "  a"}])
    with pytest.raises(IncrementalGraphError, match="unsafe characters"):
        build_incremental_graph([{"id": "a\\b"}])
    with pytest.raises(IncrementalGraphError, match="duplicate node"):
        build_incremental_graph([{"id": "a"}, {"id": "a"}])
    with pytest.raises(IncrementalGraphError, match="unknown dependency"):
        build_incremental_graph([{"id": "a", "dependencies": ["missing"]}])
    with pytest.raises(IncrementalGraphError, match="duplicate dependency"):
        build_incremental_graph([{"id": "a"}, {"id": "b", "dependencies": ["a", "a"]}])
    with pytest.raises(IncrementalGraphError, match="cost must be an integer"):
        build_incremental_graph([{"id": "a", "cost": True}])
    with pytest.raises(IncrementalGraphError, match="cost out of range"):
        build_incremental_graph([{"id": "a", "cost": 0}])
    with pytest.raises(IncrementalGraphError, match="inputs must be a mapping"):
        build_incremental_graph([{"id": "a", "inputs": ["x"]}])
    with pytest.raises(IncrementalGraphError, match="input values must be strings"):
        build_incremental_graph([{"id": "a", "inputs": {"x": 1}}])
    with pytest.raises(IncrementalGraphError, match="unknown changed node"):
        build_incremental_graph([{"id": "a"}]).invalidate(["nope"])


def test_scale_bounds_fail_closed_and_admit_the_limit() -> None:
    ok_nodes = [{"id": f"n{i:04d}"} for i in range(3)]
    graph = build_incremental_graph(ok_nodes, max_nodes=3, max_edges=3)
    assert len(graph.nodes) == 3
    with pytest.raises(IncrementalGraphError, match="node count exceeds"):
        build_incremental_graph(ok_nodes + [{"id": "n0003"}], max_nodes=3)
    with pytest.raises(IncrementalGraphError, match="edge count exceeds"):
        build_incremental_graph(
            [
                {"id": "a"},
                {"id": "b", "dependencies": ["a"]},
                {"id": "c", "dependencies": ["a", "b"]},
            ],
            max_edges=2,
        )
    with pytest.raises(IncrementalGraphError, match="visit bound"):
        build_incremental_graph(
            [
                {"id": "a"},
                {"id": "b", "dependencies": ["a"]},
                {"id": "c", "dependencies": ["b"]},
            ],
            max_visits=2,
        )
    assert MAX_NODES >= 64
    assert MAX_EDGES >= MAX_NODES
    assert MAX_TRAVERSAL_VISITS >= MAX_EDGES


def test_trusted_repo_index_snapshot_becomes_source_nodes() -> None:
    snapshot = {
        "schema": 1,
        "head": "abc",
        "object_format": "sha256",
        "source_digest": "deadbeef",
        "tracked_files": 2,
        "tracked_bytes": 8,
        "files": [
            {
                "path": "src/b.c",
                "mode": "100644",
                "index_blob": "bbb",
                "effective_blob": "BBB",
                "size": 3,
                "working_tree": True,
                "deleted": False,
            },
            {
                "path": "src/a.c",
                "mode": "100644",
                "index_blob": "aaa",
                "effective_blob": "AAA",
                "size": 3,
            },
            {
                "path": "gone.c",
                "mode": "100644",
                "index_blob": "zzz",
                "effective_blob": "zzz",
                "size": 1,
                "deleted": True,
            },
        ],
    }
    graph = build_incremental_graph(
        [{"id": "obj", "dependencies": ["src/a.c", "src/b.c"], "inputs": {"cmd": "cc"}}],
        repo_index=snapshot,
    )
    ids = [node.node_id for node in graph.nodes]
    assert ids == ["obj", "src/a.c", "src/b.c"]
    assert graph.node_map()["src/a.c"].kind == "source"
    assert "gone.c" not in graph.node_map()

    duck = SimpleNamespace(
        to_dict=lambda: snapshot,
    )
    again = build_incremental_graph(
        [{"id": "obj", "dependencies": ["src/a.c", "src/b.c"], "inputs": {"cmd": "cc"}}],
        repo_index=duck,
    )
    assert again.fingerprint == graph.fingerprint

    @dataclass(frozen=True)
    class TrackedFile:
        path: str
        mode: str
        index_blob: str
        effective_blob: str
        size: int
        working_tree: bool = False
        deleted: bool = False
        working_mode: str | None = None

    typed = SimpleNamespace(
        files=(
            TrackedFile("src/a.c", "100644", "aaa", "AAA", 3),
            TrackedFile("src/b.c", "100644", "bbb", "BBB", 3),
        ),
        schema=1,
        head="abc",
        object_format="sha256",
        source_digest="deadbeef",
        tracked_files=2,
        tracked_bytes=8,
    )
    typed_graph = build_incremental_graph(
        [{"id": "obj", "dependencies": ["src/a.c", "src/b.c"], "inputs": {"cmd": "cc"}}],
        repo_index=typed,
    )
    assert typed_graph.fingerprint == graph.fingerprint


def test_malformed_repo_index_fails_closed() -> None:
    with pytest.raises(IncrementalGraphError, match="must be a mapping"):
        build_incremental_graph(repo_index="not-a-snapshot")
    with pytest.raises(IncrementalGraphError, match="unknown keys"):
        build_incremental_graph(
            repo_index={"files": [], "execute": "make"},
        )
    with pytest.raises(IncrementalGraphError, match="files must be a sequence"):
        build_incremental_graph(repo_index={"files": {"path": "a.c"}})
    with pytest.raises(IncrementalGraphError, match="missing content digest"):
        build_incremental_graph(repo_index={"files": [{"path": "a.c", "mode": "100644"}]})
    with pytest.raises(IncrementalGraphError, match="duplicate node"):
        build_incremental_graph(
            [{"id": "src/a.c"}],
            repo_index={"files": [{"path": "src/a.c", "effective_blob": "x", "mode": "100644"}]},
        )


def test_module_does_not_import_scanner_or_execute_builds() -> None:
    source = inspect.getsource(graph_mod)
    assert "subprocess" not in source
    assert "socket" not in source
    assert "repo_intelligence" not in source
    assert "os.system" not in source
    assert graph_mod.__name__ == "skeleton.build.incremental_graph"
    assert "subprocess" not in graph_mod.__dict__
    assert "socket" not in graph_mod.__dict__
