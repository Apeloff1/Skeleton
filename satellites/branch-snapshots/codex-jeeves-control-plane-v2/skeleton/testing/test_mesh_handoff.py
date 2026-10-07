"""F-4: HandoffRegistry × AgentMesh capability-routed submit adapter."""

from __future__ import annotations

import pytest

from skeleton.agents.mesh import AgentMesh
from skeleton.kernel.errors import NoCapableAgentError
from skeleton.swarm.handoff import HandoffRegistry, TaskState
from skeleton.swarm.mesh_handoff import MeshHandoffAdapter


def test_submit_assigns_least_loaded_capable_agent():
    mesh = AgentMesh()
    busy = mesh.join({"translate"}, weight=1.0)
    busy.load = 0.8
    idle = mesh.join({"translate"}, weight=1.0)
    idle.load = 0.1
    mesh.join({"review"}, weight=1.0)  # wrong capability

    adapter = MeshHandoffAdapter(HandoffRegistry(), mesh)
    env = adapter.submit("translate", {"text": "hello"}, requester="planner")

    assert env.state is TaskState.WORKING
    assert env.assignee == str(idle.agent_id)
    assert env.capability == "translate"
    assert env.requester == "planner"


def test_submit_raises_when_no_capable_agent():
    mesh = AgentMesh()
    mesh.join({"review"})
    adapter = MeshHandoffAdapter(HandoffRegistry(), mesh)
    with pytest.raises(NoCapableAgentError):
        adapter.submit("translate", {}, requester="planner")
    # No orphan envelope left behind (route-before-submit).
    assert adapter.registry.stats()["tasks"] == 0


def test_adapter_stats_compose_both_sides():
    mesh = AgentMesh()
    mesh.join({"npc"})
    adapter = MeshHandoffAdapter(HandoffRegistry(), mesh)
    adapter.submit("npc", {"desc": "ferryman"}, requester="api")
    stats = adapter.stats()
    assert stats["mesh"]["agents"] == 1
    assert stats["handoff"]["tasks"] == 1
    assert stats["handoff"]["by_state"].get("working") == 1
