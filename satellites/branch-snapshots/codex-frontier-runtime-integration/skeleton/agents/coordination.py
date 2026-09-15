"""
Skeleton Agents — Coordination and task management

Provides:
- Coordinator: Central task coordinator for agent dispatch
- Task: Typed task with priority and constraints
- AgentPool: Manage agent lifecycle and resource allocation
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

from skeleton.kernel.events import DomainEvent, EventBus


class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class Task:
    """A single unit of work for an agent."""
    task_id: str
    description: str
    priority: int = 1  # Higher = more urgent
    status: TaskStatus = TaskStatus.PENDING
    agent_id: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=__import__('time').time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status.name,
            "agent_id": self.agent_id,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class AgentPool:
    """Manage agent lifecycle and resource allocation."""

    def __init__(self, max_agents: int = 16, bus: Optional[EventBus] = None):
        self.max_agents = max_agents
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._bus = bus
        self._stats = {"created": 0, "destroyed": 0, "tasks_assigned": 0}

    def create(self, specialisations: Set[str], capacity: int = 5) -> str:
        """Create a new agent and return its ID."""
        if len(self._agents) >= self.max_agents:
            raise RuntimeError(f"Agent pool at capacity ({self.max_agents})")
        
        agent_id = str(uuid.uuid4())[:8]
        self._agents[agent_id] = {
            "specialisations": set(specialisations),
            "capacity": capacity,
            "load": 0,
            "tasks": [],
            "created_at": __import__('time').time(),
        }
        self._stats["created"] += 1
        
        if self._bus:
            self._bus.emit("agents.pool.created", {"agent_id": agent_id, "specialisations": list(specialisations)})
        
        return agent_id

    def assign(self, agent_id: str, task: Task) -> bool:
        """Assign a task to an agent."""
        if agent_id not in self._agents:
            return False
        
        agent = self._agents[agent_id]
        if agent["load"] >= agent["capacity"]:
            return False
        
        agent["tasks"].append(task.task_id)
        agent["load"] += 1
        task.agent_id = agent_id
        task.status = TaskStatus.RUNNING
        self._stats["tasks_assigned"] += 1
        
        if self._bus:
            self._bus.emit("agents.task.assigned", {"agent_id": agent_id, "task_id": task.task_id})
        
        return True

    def release(self, agent_id: str, task_id: str) -> None:
        """Release a completed task from an agent."""
        if agent_id in self._agents:
            agent = self._agents[agent_id]
            if task_id in agent["tasks"]:
                agent["tasks"].remove(task_id)
                agent["load"] = max(0, agent["load"] - 1)

    def find_capable(self, specialisation: str) -> List[str]:
        """Find agents with a given specialisation, sorted by load."""
        capable = [
            (aid, agent["load"])
            for aid, agent in self._agents.items()
            if specialisation in agent["specialisations"]
        ]
        capable.sort(key=lambda x: x[1])
        return [aid for aid, _ in capable]

    def destroy(self, agent_id: str) -> None:
        """Remove an agent from the pool."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._stats["destroyed"] += 1

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "active": len(self._agents),
            "max": self.max_agents,
            "total_load": sum(a["load"] for a in self._agents.values()),
        }


class Coordinator:
    """Central coordinator for dispatching tasks to capable agents."""

    def __init__(self, pool: Optional[AgentPool] = None, bus: Optional[EventBus] = None):
        self.pool = pool or AgentPool(bus=bus)
        self._bus = bus
        self._tasks: Dict[str, Task] = {}
        self._handlers: Dict[str, Callable[[Task], Any]] = {}
        self._stats = {"dispatched": 0, "completed": 0, "failed": 0}

    def register_handler(self, task_type: str, handler: Callable[[Task], Any]) -> None:
        """Register a handler for a specific task type."""
        self._handlers[task_type] = handler

    def dispatch(self, description: str, task_type: str = "default", priority: int = 1, specialisation: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Task:
        """Dispatch a new task to the agent pool."""
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            description=description,
            priority=priority,
            metadata=metadata or {},
        )
        self._tasks[task.task_id] = task
        
        # Find capable agent
        spec = specialisation or task_type
        candidates = self.pool.find_capable(spec)
        
        if not candidates:
            # Create a new agent if pool has capacity
            try:
                agent_id = self.pool.create({spec})
                candidates = [agent_id]
            except RuntimeError:
                task.status = TaskStatus.FAILED
                task.error = f"No agents available for specialisation: {spec}"
                self._stats["failed"] += 1
                return task
        
        # Assign to least loaded capable agent
        assigned = self.pool.assign(candidates[0], task)
        if not assigned:
            task.status = TaskStatus.FAILED
            task.error = "Agent at capacity"
            self._stats["failed"] += 1
            return task
        
        self._stats["dispatched"] += 1
        
        # Execute handler if available
        handler = self._handlers.get(task_type)
        if handler:
            try:
                task.result = handler(task)
                task.status = TaskStatus.COMPLETED
                self._stats["completed"] += 1
                self.pool.release(task.agent_id, task.task_id)
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                self._stats["failed"] += 1
        
        if self._bus:
            self._bus.emit("agents.coordinator.dispatched", {
                "task_id": task.task_id,
                "agent_id": task.agent_id,
                "status": task.status.name,
            })
        
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "pending": len([t for t in self._tasks.values() if t.status == TaskStatus.PENDING]),
            "running": len([t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]),
            "completed": len([t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]),
            "failed": len([t for t in self._tasks.values() if t.status == TaskStatus.FAILED]),
            "total": len(self._tasks),
        }
