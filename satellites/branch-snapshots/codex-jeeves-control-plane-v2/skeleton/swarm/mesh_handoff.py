"""HandoffRegistry × AgentMesh adapter — capability-routed envelope assign.

F-4: ``HandoffRegistry.submit`` creates envelopes without an assignee;
``AgentMesh.route(capability)`` picks the least-loaded healthy agent.
This adapter is the single composition point: route first, then submit,
then ``accept`` with the chosen assignee.

Deliberately does **not** fold ``AgentMesh`` and ``SwarmMesh`` (see
``mesh_boundary``). Operates only on the operational ``AgentMesh`` the
API already wires.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.agents.mesh import AgentMesh
from skeleton.swarm.handoff import HandoffRegistry, TaskEnvelope


class MeshHandoffAdapter:
    """Submit A2A envelopes with assignee chosen by AgentMesh capability routing."""

    def __init__(self, registry: HandoffRegistry, mesh: AgentMesh) -> None:
        self.registry = registry
        self.mesh = mesh

    def submit(
        self,
        capability: str,
        input: Dict[str, Any],
        *,
        requester: str,
    ) -> TaskEnvelope:
        """Route by capability, submit envelope, accept with the chosen agent.

        Raises ``NoCapableAgentError`` from ``AgentMesh.route`` when no
        healthy agent advertises ``capability`` (no envelope is created).
        """
        agent = self.mesh.route(capability)
        env = self.registry.submit(capability, input, requester=requester)
        return self.registry.accept(env.task_id, assignee=str(agent.agent_id))

    def stats(self) -> Dict[str, Any]:
        return {
            "handoff": self.registry.stats(),
            "mesh": self.mesh.stats(),
        }
