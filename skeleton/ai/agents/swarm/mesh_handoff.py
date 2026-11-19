"""Handoff protocol card. Delegates to Mesh."""

from __future__ import annotations

from skeleton.automation.swarm.mesh import Mesh
from skeleton.automation.agents.mesh import AgentMesh
from skeleton.automation.swarm.handoff import HandoffRegistry, TaskEnvelope


class MeshHandoffAdapter:
    """Route tasks before creating envelopes, avoiding unassignable orphans.

    AgentMesh owns selection and liveness; HandoffRegistry owns task state
    and emits the submission/acceptance events. This adapter executes no work.
    """

    def __init__(self, registry: HandoffRegistry, mesh: AgentMesh) -> None:
        self.registry = registry
        self.mesh = mesh

    def submit(self, capability: str, input: dict, *, requester: str) -> TaskEnvelope:
        agent = self.mesh.route(capability)
        envelope = self.registry.submit(capability, input, requester=requester)
        return self.registry.accept(envelope.task_id, assignee=str(agent.agent_id))

    def stats(self) -> dict:
        return {"mesh": self.mesh.stats(), "handoff": self.registry.stats()}


def handoff(a: str, b: str, task: str, mesh: Mesh | None = None) -> dict:
    return (mesh or Mesh()).handoff(a, b, task)
