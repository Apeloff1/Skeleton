"""
Skeleton Agents Package

Exports:
- Coordinator: Central task coordinator
- AgentPool: Agent lifecycle management
- Task / TaskStatus: Typed task with status tracking
- MeshBridge: Route coordinator tasks onto a live SwarmMesh
"""

from skeleton.agents.coordination import AgentPool, Coordinator, Task, TaskStatus
from skeleton.agents.bridge import MeshBridge

__all__ = [
    "Coordinator",
    "AgentPool",
    "Task",
    "TaskStatus",
    "MeshBridge",
]
