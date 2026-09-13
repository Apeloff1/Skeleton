"""
Skeleton Agents Package

Exports the coordination, mesh bridge, and bounded swarm runtime primitives used
by API workers and embedded orchestration clients.
"""

from skeleton.agents.coordination import AgentPool, Coordinator, Task, TaskStatus
from skeleton.agents.bridge import MeshBridge
from skeleton.agents.swarm_runtime import (
    AdmissionError,
    LeaseError,
    RuntimeSnapshot,
    SwarmRuntime,
    SwarmTask,
    TaskState,
    WorkerState,
)

__all__ = [
    "Coordinator",
    "AgentPool",
    "Task",
    "TaskStatus",
    "MeshBridge",
    "AdmissionError",
    "LeaseError",
    "RuntimeSnapshot",
    "SwarmRuntime",
    "SwarmTask",
    "TaskState",
    "WorkerState",
]
