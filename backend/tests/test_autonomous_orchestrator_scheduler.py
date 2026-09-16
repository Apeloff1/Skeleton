from __future__ import annotations

from types import SimpleNamespace

from core import autonomous_orchestrator as orchestrator


def _node(node_id: str, *, depends_on=(), status: str = "planned") -> dict:
    return {
        "id": node_id,
        "kind": "forge",
        "target": "test",
        "text": node_id,
        "tier": None,
        "model": None,
        "depends_on": list(depends_on),
        "status": status,
        "result": {"old": True} if status == "done" else None,
        "produced_gid": f"gid-{node_id}" if status == "done" else None,
    }


def _plan(nodes) -> dict:
    return {
        "plan_id": "plan-1",
        "build_id": "build-1",
        "directive": "test",
        "version": 1,
        "nodes": nodes,
        "node_count": len(nodes),
        "status": "planned",
        "created": 0.0,
    }


def _install_plan(monkeypatch, plan: dict) -> None:
    monkeypatch.setattr(orchestrator, "get_plan", lambda plan_id: plan if plan_id == "plan-1" else None)
    monkeypatch.setattr(orchestrator, "_save_plan", lambda saved: None)

    # Keep execution tests hermetic even when the optional provenance module is
    # available in the full backend environment.
    import core

    monkeypatch.setattr(
        core,
        "provenance_ledger",
        SimpleNamespace(append=lambda *args, **kwargs: None),
        raising=False,
    )


def test_failed_node_is_attempted_once_per_execute_call(monkeypatch):
    plan = _plan([_node("n1")])
    _install_plan(monkeypatch, plan)
    attempts: list[str] = []

    def fail_once(build_id, node, by_id):
        attempts.append(node["id"])
        node["status"] = "error"
        return {"error": "persistent failure"}

    monkeypatch.setattr(orchestrator, "_exec_node", fail_once)

    first = orchestrator.execute_plan("plan-1")
    assert attempts == ["n1"]
    assert first["status"] == "partial"
    assert first["error"] == 1

    # A later invocation may retry the prior error, but it still gets only one
    # attempt in that invocation rather than spinning inside the worker.
    second = orchestrator.execute_plan("plan-1")
    assert attempts == ["n1", "n1"]
    assert second["error"] == 1


def test_ready_queue_executes_each_dag_node_once_after_dependencies(monkeypatch):
    nodes = [
        _node("n4", depends_on=("n2", "n3")),
        _node("n3", depends_on=("n1",)),
        _node("n2", depends_on=("n1",)),
        _node("n1"),
    ]
    plan = _plan(nodes)
    _install_plan(monkeypatch, plan)
    execution_order: list[str] = []

    def succeed(build_id, node, by_id):
        execution_order.append(node["id"])
        node["status"] = "done"
        node["produced_gid"] = f"gid-{node['id']}"
        return {"ok": True}

    monkeypatch.setattr(orchestrator, "_exec_node", succeed)

    result = orchestrator.execute_plan("plan-1")
    assert result["status"] == "done"
    assert result["done"] == 4
    assert sorted(execution_order) == ["n1", "n2", "n3", "n4"]
    assert len(execution_order) == len(set(execution_order))

    position = {node_id: index for index, node_id in enumerate(execution_order)}
    assert position["n1"] < position["n2"]
    assert position["n1"] < position["n3"]
    assert position["n2"] < position["n4"]
    assert position["n3"] < position["n4"]


def test_failed_dependency_does_not_unlock_descendants(monkeypatch):
    plan = _plan([_node("n1"), _node("n2", depends_on=("n1",))])
    _install_plan(monkeypatch, plan)
    attempts: list[str] = []

    def fail_root(build_id, node, by_id):
        attempts.append(node["id"])
        node["status"] = "error"
        return {"error": "root failed"}

    monkeypatch.setattr(orchestrator, "_exec_node", fail_root)

    result = orchestrator.execute_plan("plan-1")
    assert attempts == ["n1"]
    assert result["nodes"][1]["status"] == "planned"
    assert result["status"] == "partial"


def test_replan_uses_reverse_edge_bfs_without_fixed_point_rescans(monkeypatch):
    class CountingNodes(list):
        def __init__(self, rows):
            super().__init__(rows)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    chain = [
        _node(f"n{index}", depends_on=(() if index == 0 else (f"n{index - 1}",)), status="done")
        for index in range(80)
    ]
    # Reverse order makes the previous fixed-point implementation require one
    # whole-plan pass per level of the chain.
    nodes = CountingNodes(reversed(chain))
    plan = _plan(nodes)
    _install_plan(monkeypatch, plan)

    result = orchestrator.replan_from("plan-1", "n0")
    iterations_after_replan = nodes.iterations

    assert len(result["replanned"]) == 80
    assert all(node["status"] == "planned" for node in nodes)
    assert all(node["result"] is None for node in nodes)
    assert all(node["produced_gid"] is None for node in nodes)
    assert plan["version"] == 2
    # Measure only replan_from itself; the validation traversals above also
    # iterate CountingNodes and must not be charged to the scheduler.
    assert iterations_after_replan <= 4
