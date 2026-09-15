"""
Skeleton Swarm-Agents Bridge — route Coordinator tasks through the mesh

Provides:
- MeshBridge: Maps agent specialisations between the two systems,
  letting the Coordinator dispatch onto the live SwarmMesh while
  keeping AgentPool bookkeeping.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from skeleton.kernel.events import EventBus


class MeshBridge:
    """Bridge the Coordinator's AgentPool onto a live SwarmMesh.

    The Coordinator owns task lifecycle (Task, status, results);
    the SwarmMesh owns capability routing. The bridge lets a
    Coordinator dispatch tasks onto mesh agents directly, so
    genesis-wired swarms get task bookkeeping for free.
    """

    def __init__(self, mesh: Any, bus: Optional[EventBus] = None):
        self._mesh = mesh
        self._bus = bus
        self._assignments: Dict[str, str] = {}  # task_id -> mesh agent_id
        self._stats = {"bridged": 0, "failed": 0}

    def register_pool_agent(self, specialisations: Set[str], weight: float = 1.0) -> Optional[str]:
        """Join the mesh and return the mesh agent id."""
        agent = self._mesh.join(set(specialisations), weight=weight)
        return agent.agent_id if agent else None

    def dispatch(self, task: Any, specialisation: str) -> bool:
        """Route a Coordinator task through the mesh.

        On success, stamps task.metadata with the mesh agent id and
        records the assignment. Caller still owns execution/result.
        """
        agent = self._mesh.route(specialisation)
        if agent is None:
            self._stats["failed"] += 1
            return False

        self._assignments[task.task_id] = agent.agent_id
        task.metadata["mesh_agent_id"] = agent.agent_id
        self._stats["bridged"] += 1

        if self._bus:
            self._bus.emit("agents.bridge.dispatched", {
                "task_id": task.task_id,
                "mesh_agent_id": agent.agent_id,
                "specialisation": specialisation,
            })
        return True

    def release(self, task_id: str) -> None:
        """Mark a bridged task complete (releases mesh load implicitly
        via heartbeat decay on the agent's next route cycle)."""
        self._assignments.pop(task_id, None)

    def assignment_for(self, task_id: str) -> Optional[str]:
        return self._assignments.get(task_id)

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "active_assignments": len(self._assignments)}
