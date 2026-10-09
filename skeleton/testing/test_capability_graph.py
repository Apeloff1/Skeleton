"""Adversarial and integration tests for bounded deterministic graph execution."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.capability_graph import (
    SCHEMA, MAX_GRAPH_BYTES, MAX_GRAPH_NODES, CapabilityGraphError,
    execute_capability_graph, execute_capability_graph_json,
)


def graph(nodes, outputs):
    return {"schema_version": SCHEMA, "nodes": nodes, "outputs": outputs}


def node(name, op, **args):
    return {"id": name, "operation": op, "args": args}


def test_gameplay_graph_chains_damage_inventory_score_and_motion_without_training():
    payload = graph([
        node("damage_one", "game.damage", health=20, damage=5),
        node("damage_two", "game.damage",
             health={"$ref": "damage_one"}, damage=7),
        node("points", "game.coins", coins=3, points_per_coin=10),
        node("score", "math.add",
             a={"$ref": "damage_two"}, b={"$ref": "points"}),
        node("integrated", "physics.integrate_2d",
             position={"x": 1, "y": 2}, velocity={"x": 2, "y": 1},
             acceleration={"x": 1, "y": 0}, ticks=3),
        node("moved", "grid.move",
             position={"$ref": "integrated", "path": ["position"]},
             delta={"x": 1, "y": -1}),
        node("x_final", "math.add",
             a={"$ref": "moved", "path": ["x"]}, b=5),
    ], ["score", "moved", "x_final"])
    before = copy.deepcopy(payload)
    result = execute_capability_graph(payload)
    assert payload == before
    assert result["node_count"] == 7
    assert result["outputs"] == {
        "score": 38, "moved": {"x": 14, "y": 4}, "x_final": 19,
    }
    assert result == execute_capability_graph(payload)
    assert len(result["graph_sha256"]) == 64
    assert len(result["node_receipts"]) == 7
    assert all(len(item["result_sha256"]) == 64 for item in result["node_receipts"])
    assert result["training_examples_added"] == 0
    assert result["model_inference_used"] is False
    assert result["network_access_used"] is False
    assert result["filesystem_access_used"] is False
    assert result["executor_authority_granted"] is False


def test_graph_resolves_list_indices_without_executing_untrusted_strings():
    payload = graph([
        node("events", "events.order",
             events=[{"name": "late", "tick": 9},
                     {"name": "first", "tick": 1},
                     {"name": "second", "tick": 1}]),
        node("picked", "content.sha256",
             text={"$ref": "events", "path": [0]}),
    ], ["picked"])
    result = execute_capability_graph(payload)
    assert result["outputs"]["picked"] == hashlib.sha256(b"first").hexdigest()


def test_graph_fences_forward_and_self_references_before_any_node_execution():
    payloads = [
        graph([node("alpha", "math.add", a={"$ref": "alpha"}, b=1)], ["alpha"]),
        graph([node("alpha", "math.add", a={"$ref": "future"}, b=1),
               node("future", "math.add", a=1, b=2)], ["alpha"]),
        graph([node("alpha", "math.add", a={"$ref": "missing"}, b=1)], ["alpha"]),
        graph([node("alpha", "math.add",
                    a={"$ref": "beta"}, b=1),
               node("beta", "math.add",
                    a={"$ref": "alpha"}, b=1)], ["alpha"]),
    ]
    for item in payloads:
        with pytest.raises(CapabilityGraphError, match="reference"):
            execute_capability_graph(item)


@pytest.mark.parametrize("broken", [
    {"schema_version": SCHEMA, "nodes": [], "outputs": ["x"]},
    {"schema_version": SCHEMA, "nodes": [
        node("a", "math.add", a=1, b=2)], "outputs": []},
    {"schema_version": SCHEMA + "-wrong", "nodes": [
        node("a", "math.add", a=1, b=2)], "outputs": ["a"]},
    graph([node("a", "math.add", a=1, b=2),
           node("a", "math.add", a=2, b=3)], ["a"]),
    graph([node("a", "math.add", a=1, b=2)], ["a", "a"]),
    graph([node("a", "math.add", a=1, b=2)], ["absent"]),
    graph([node("a", "os.system", command="rm -rf /")], ["a"]),
    graph([node("__class__", "math.add", a=1, b=2)], ["__class__"]),
    graph([node("a", "math.add", a=True, b=1)], ["a"]),
    graph([node("a", "math.add", a=1, b=2)], ["a"]).__or__({"exotic": 1}),
])
def test_ambiguous_unadmitted_graphs_fail_closed(broken):
    with pytest.raises(CapabilityGraphError):
        execute_capability_graph(broken)


def test_graphs_enforce_node_caps_without_silent_partial_result():
    nodes = [node(f"n{x}", "math.add", a=1, b=x)
             for x in range(MAX_GRAPH_NODES + 1)]
    with pytest.raises(CapabilityGraphError, match="count"):
        execute_capability_graph(graph(nodes, ["n0"]))
    accepted = execute_capability_graph(graph(nodes[:-1], ["n31"]))
    assert accepted["node_count"] == MAX_GRAPH_NODES
    assert accepted["outputs"]["n31"] == 32


def test_graph_reference_paths_validate_type_index_and_access():
    skeleton = [node("a", "grid.move",
                     position={"x": 0, "y": 0},
                     delta={"x": 1, "y": 0})]
    for path in (
        ["missing"], ["x", "not-an-object"],
        [0], [True], ["x"] * 13,
    ):
        trial = graph(skeleton + [
            node("b", "math.add", a={"$ref": "a", "path": path}, b=1),
        ], ["b"])
        with pytest.raises(CapabilityGraphError, match="reference"):
            execute_capability_graph(trial)


def test_nested_reference_depth_is_bounded():
    nested = 1
    for _ in range(15):
        nested = {"wrapped": nested}
    payload = graph([node("a", "json.select", object=nested, keys=["wrapped"])], ["a"])
    # This input may be small, but resolution depth is still bounded.
    with pytest.raises(CapabilityGraphError, match="nesting"):
        execute_capability_graph(payload)


def test_graph_requires_canonical_json_and_rejects_duplicate_keys():
    payloads = [
        b'{"schema_version":"' + SCHEMA.encode() +
        b'","nodes":[],"nodes":[],"outputs":[]}',
        b'{"schema_version":"' + SCHEMA.encode() +
        b'","nodes":[],"outputs":[],"metadata":NaN}',
        b'{"schema_version":"' + SCHEMA.encode() +
        b'","nodes":[],"outputs":[],"metadata":Infinity}',
        b'\xff\xff',
        b'["not","a","graph"]',
        b'{"broken":',
        b' ' * (MAX_GRAPH_BYTES + 1),
    ]
    for raw in payloads:
        with pytest.raises(CapabilityGraphError):
            execute_capability_graph_json(raw)


def test_graph_hash_is_stable_across_equivalent_json_key_orders():
    base = graph([node("a", "math.add", a=1, b=2)], ["a"])
    flipped = {"outputs": ["a"], "nodes": [
        {"args": {"b": 2, "a": 1}, "operation": "math.add", "id": "a"},
    ], "schema_version": SCHEMA}
    result = execute_capability_graph(base)
    assert result["graph_sha256"] == execute_capability_graph(flipped)["graph_sha256"]


def test_graph_cannot_grant_execution_permissions():
    payload = graph([
        node("decision", "policy.local_action",
             action="read_local_text", operator_selected=True),
        node("plain", "json.select",
             object={"policy": {"$ref": "decision"}}, keys=["policy"]),
    ], ["plain"])
    result = execute_capability_graph(payload)
    assert result["outputs"]["plain"]["policy"]["policy_allow"] is True
    assert result["outputs"]["plain"]["policy"]["executor_permission_granted"] is False
    assert result["executor_authority_granted"] is False


def test_frozen_console_and_unified_cli_run_same_graph_without_model(
    tmp_path: Path, capsys,
):
    from skeleton.app.offline_cli import main as console
    from skeleton.app.cli import run_app_cli

    payload = graph([
        node("health", "game.damage", health=10, damage=3),
        node("final", "math.add", a={"$ref": "health"}, b=5),
    ], ["final"])
    file = tmp_path / "graph.json"
    file.write_text(json.dumps(payload), "utf-8")
    assert console(["--capability-graph-file", str(file), "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["outputs"] == {"final": 12}
    assert run_app_cli([
        "local-ai", "--capability-graph-file", str(file), "--json",
    ]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first == second


def test_graph_console_rejects_invalid_input_and_conflicting_states(
    tmp_path: Path, capsys,
):
    from skeleton.app.offline_cli import main as console

    file = tmp_path / "graph.json"
    file.write_text('{"schema_version":"unsupported","nodes":[],"outputs":[]}', "utf-8")
    assert console(["--capability-graph-file", str(file), "--json"]) == 1
    assert console([
        "--capability-graph-file", str(file), "--queue-status",
    ]) == 2
    assert console([
        "--capability-graph-file", str(file), "--model", "missing.json",
    ]) == 2
    assert capsys.readouterr().out == ""
