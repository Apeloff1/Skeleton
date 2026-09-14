import pytest

from core import autonomous_orchestrator as orch
from core.jeeves_execution_kernel import (
    BudgetExceeded,
    CancellationToken,
    ExecutionBudget,
    ExecutionCancelled,
    ExecutionContext,
)


def _plan():
    return {
        "plan_id": "p1",
        "build_id": "b1",
        "status": "planned",
        "nodes": [
            {"id": "n1", "kind": "forge", "depends_on": [], "status": "planned",
             "target": "a", "result": None, "produced_gid": None},
            {"id": "n2", "kind": "gate", "depends_on": ["n1"], "status": "planned",
             "target": None, "result": None, "produced_gid": None},
        ],
    }


def test_execute_plan_records_node_evidence(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(orch, "get_plan", lambda _pid: plan)
    monkeypatch.setattr(orch, "_save_plan", lambda _p: None)

    def fake_exec(_build_id, node, _by_id):
        node["status"] = "done"
        node["produced_gid"] = node["id"]
        return {"ok": True}

    monkeypatch.setattr(orch, "_exec_node", fake_exec)
    ctx = ExecutionContext(budget=ExecutionBudget(max_steps=2))
    result = orch.execute_plan("p1", execution=ctx)
    assert result["status"] == "done"
    assert result["execution"]["budget"]["steps"] == 2
    assert [e["data"].get("label") for e in ctx.evidence()
            if e["kind"] == "checkpoint"] == [
                "orchestrator.node.start", "orchestrator.node.start"
            ]


def test_execute_plan_honors_cancel_between_nodes(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(orch, "get_plan", lambda _pid: plan)
    monkeypatch.setattr(orch, "_save_plan", lambda _p: None)
    token = CancellationToken()

    def fake_exec(_build_id, node, _by_id):
        node["status"] = "done"
        if node["id"] == "n1":
            token.cancel("superseded")
        return {"ok": True}

    monkeypatch.setattr(orch, "_exec_node", fake_exec)
    ctx = ExecutionContext(cancellation=token, budget=ExecutionBudget(max_steps=5))
    with pytest.raises(ExecutionCancelled, match="superseded"):
        orch.execute_plan("p1", execution=ctx)
    assert plan["nodes"][0]["status"] == "done"
    assert plan["nodes"][1]["status"] == "planned"


def test_execute_plan_enforces_step_budget(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(orch, "get_plan", lambda _pid: plan)
    monkeypatch.setattr(orch, "_save_plan", lambda _p: None)

    def fake_exec(_build_id, node, _by_id):
        node["status"] = "done"
        return {"ok": True}

    monkeypatch.setattr(orch, "_exec_node", fake_exec)
    ctx = ExecutionContext(budget=ExecutionBudget(max_steps=1))
    with pytest.raises(BudgetExceeded):
        orch.execute_plan("p1", execution=ctx)
    assert plan["nodes"][0]["status"] == "done"
    assert plan["nodes"][1]["status"] == "planned"


def test_cancel_unknown_job_is_safe():
    result = orch.cancel_job("not-real")
    assert result == {"job_id": "not-real", "status": "unknown", "cancelled": False}
