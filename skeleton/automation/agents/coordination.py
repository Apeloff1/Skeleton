"""
Skeleton Agents — compatibility coordination and task management.

The legacy AgentPool remains responsible for worker-capacity allocation, while
registered handler execution is adapted through the canonical frontier
orchestrator so run/tool terminal-state handling has one authority.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

from skeleton.frontier.orchestration import (
    OrchestrationDriver,
    RunRecord,
    RunStatus,
    ToolInvocation,
    ToolRegistry,
    ToolResult,
    TurnOutcome,
)
from skeleton.kernel.events import EventBus
from skeleton.observability.orchestration import ObservableOrchestrator


class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


def _positive_int(value: object, name: str) -> int:
    """Validate positive integer configuration without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


@dataclass
class Task:
    """A single compatibility task projected from a canonical run when local."""

    task_id: str
    description: str
    priority: int = 1  # Higher = more urgent
    status: TaskStatus = TaskStatus.PENDING
    agent_id: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

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


def _task_correlation_id(task: Task) -> str:
    """Resolve bounded correlation metadata, falling back to the task ID."""
    for key in ("correlation_id", "request_id", "run_id", "rid"):
        candidate = task.metadata.get(key)
        if (
            isinstance(candidate, str)
            and candidate
            and candidate == candidate.strip()
            and len(candidate) <= 128
        ):
            return candidate
    return task.task_id


class AgentPool:
    """Manage legacy agent lifecycle and resource allocation."""

    def __init__(self, max_agents: int = 16, bus: Optional[EventBus] = None):
        self.max_agents = _positive_int(max_agents, "max_agents")
        self._agents: Dict[str, Dict[str, Any]] = {}
        # Capacity ownership is keyed by logical task ID, not Task object
        # identity. This prevents two independently-created Task instances with
        # the same ID from consuming multiple agent slots.
        self._task_owners: Dict[str, str] = {}
        # Keep only currently-owned task objects so destructive agent lifecycle
        # changes can terminalize the exact task before its logical ID is reused.
        self._owned_tasks: Dict[str, Task] = {}
        self._bus = bus
        self._stats = {"created": 0, "destroyed": 0, "tasks_assigned": 0}

    def create(self, specialisations: Set[str], capacity: int = 5) -> str:
        """Create a new agent and return its ID."""
        capacity = _positive_int(capacity, "capacity")
        if len(self._agents) >= self.max_agents:
            raise RuntimeError(f"Agent pool at capacity ({self.max_agents})")

        agent_id = str(uuid.uuid4())[:8]
        self._agents[agent_id] = {
            "specialisations": set(specialisations),
            "capacity": capacity,
            "load": 0,
            "tasks": [],
            "created_at": time.time(),
        }
        self._stats["created"] += 1

        if self._bus:
            self._bus.emit(
                "agents.pool.created",
                {
                    "agent_id": agent_id,
                    "specialisations": sorted(specialisations),
                },
            )

        return agent_id

    def assign(self, agent_id: str, task: Task) -> bool:
        """Assign a pending, globally-unowned task to an agent."""
        if agent_id not in self._agents:
            return False

        # A logical task may own exactly one agent slot. Object-local state
        # prevents reuse of the same Task instance, while the owner registry
        # closes the distinct-object/same-task-id duplication path.
        if (
            task.status is not TaskStatus.PENDING
            or task.agent_id is not None
            or task.task_id in self._task_owners
        ):
            return False

        agent = self._agents[agent_id]
        if agent["load"] >= agent["capacity"]:
            return False

        agent["tasks"].append(task.task_id)
        agent["load"] += 1
        self._task_owners[task.task_id] = agent_id
        self._owned_tasks[task.task_id] = task
        task.agent_id = agent_id
        task.status = TaskStatus.RUNNING
        self._stats["tasks_assigned"] += 1

        if self._bus:
            self._bus.emit(
                "agents.task.assigned",
                {"agent_id": agent_id, "task_id": task.task_id},
                correlation_id=_task_correlation_id(task),
            )

        return True

    def release(self, agent_id: str, task_id: str) -> None:
        """Release a task only from the agent that currently owns its slot."""
        if self._task_owners.get(task_id) != agent_id:
            return
        if agent_id not in self._agents:
            return

        agent = self._agents[agent_id]
        if task_id not in agent["tasks"]:
            return

        agent["tasks"].remove(task_id)
        agent["load"] = max(0, agent["load"] - 1)
        self._task_owners.pop(task_id, None)
        self._owned_tasks.pop(task_id, None)

    def find_capable(self, specialisation: str) -> List[str]:
        """Find available agents with a given specialisation, sorted by load."""
        capable = [
            (aid, agent["load"])
            for aid, agent in self._agents.items()
            if specialisation in agent["specialisations"]
            and agent["load"] < agent["capacity"]
        ]
        capable.sort(key=lambda item: item[1])
        return [aid for aid, _ in capable]

    def destroy(self, agent_id: str) -> None:
        """Remove an agent and cancel every running task whose slot it held."""
        agent = self._agents.pop(agent_id, None)
        if agent is None:
            return

        for task_id in tuple(agent["tasks"]):
            if self._task_owners.get(task_id) != agent_id:
                continue
            self._task_owners.pop(task_id, None)
            task = self._owned_tasks.pop(task_id, None)
            if task is not None and task.status is TaskStatus.RUNNING:
                task.status = TaskStatus.CANCELLED
                task.error = "Assigned agent was destroyed before task completion"
        self._stats["destroyed"] += 1

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "active": len(self._agents),
            "max": self.max_agents,
            "total_load": sum(agent["load"] for agent in self._agents.values()),
        }


@dataclass(slots=True)
class _CoordinatorDriver(OrchestrationDriver):
    """Adapt one registered legacy handler to the canonical two-turn lifecycle."""

    task_id: str
    task_type: str
    requested: bool = False

    async def next_turn(
        self,
        *,
        run: RunRecord,
        tool_results: tuple[ToolResult, ...],
    ) -> TurnOutcome:
        del run
        if not self.requested:
            self.requested = True
            return TurnOutcome(
                tool_calls=(
                    ToolInvocation(
                        call_id=self.task_id,
                        name=self.task_type,
                        arguments={"task_id": self.task_id},
                    ),
                )
            )

        if len(tool_results) != 1 or tool_results[0].call_id != self.task_id:
            raise RuntimeError("legacy coordinator received invalid tool result")
        return TurnOutcome(output=tool_results[0].output, terminal=True)


class Coordinator:
    """Compatibility coordinator backed by the canonical orchestration lifecycle.

    Agent selection/capacity remains local to :class:`AgentPool`. When a local
    handler is registered, its execution and terminal state are owned by
    :class:`ObservableOrchestrator`; ``TaskStatus`` is only a compatibility
    projection of the resulting ``RunRecord``.
    """

    def __init__(self, pool: Optional[AgentPool] = None, bus: Optional[EventBus] = None):
        self._tasks: Dict[str, Task] = {}
        self._handlers: Dict[str, Callable[[Task], Any]] = {}
        self._runs: Dict[str, RunRecord] = {}
        self._tools = ToolRegistry()
        effective_bus = bus
        if effective_bus is None and pool is not None:
            effective_bus = pool._bus
        self._orchestrator = ObservableOrchestrator(
            tools=self._tools,
            event_bus=effective_bus,
        )
        self._bus = self._orchestrator.event_bus
        self.pool = pool or AgentPool(bus=self._bus)
        self._registered_tool_types: Set[str] = set()
        self._stats = {"dispatched": 0, "completed": 0, "failed": 0}

    def register_handler(self, task_type: str, handler: Callable[[Task], Any]) -> None:
        """Register or replace a handler for a specific compatibility task type."""
        if not callable(handler):
            raise TypeError("handler must be callable")
        if task_type not in self._registered_tool_types:

            def invoke(arguments: Dict[str, Any], *, _task_type: str = task_type) -> Any:
                task_id = arguments.get("task_id")
                if not isinstance(task_id, str):
                    raise RuntimeError("legacy coordinator tool call missing task_id")
                task = self._tasks.get(task_id)
                if task is None:
                    raise RuntimeError(f"legacy coordinator task not found: {task_id}")
                current_handler = self._handlers.get(_task_type)
                if current_handler is None:
                    raise RuntimeError(
                        f"legacy coordinator handler not found: {_task_type}"
                    )
                return current_handler(task)

            self._tools.register(task_type, invoke)
            self._registered_tool_types.add(task_type)
        self._handlers[task_type] = handler

    def _prepare_task(
        self,
        description: str,
        *,
        task_type: str,
        priority: int,
        specialisation: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Task:
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            description=description,
            priority=priority,
            metadata=dict(metadata or {}),
        )
        self._tasks[task.task_id] = task

        spec = specialisation or task_type
        candidates = self.pool.find_capable(spec)

        # Capacity can change between discovery and assignment. Try every
        # currently available candidate before expanding the pool.
        assigned = False
        for agent_id in candidates:
            if self.pool.assign(agent_id, task):
                assigned = True
                break

        if not assigned:
            try:
                agent_id = self.pool.create({spec})
            except RuntimeError:
                task.status = TaskStatus.FAILED
                task.error = f"No agents available for specialisation: {spec}"
                self._stats["failed"] += 1
                return task

            assigned = self.pool.assign(agent_id, task)
            if not assigned:
                # A newly-created agent that cannot accept its first task must
                # not consume a pool slot indefinitely.
                self.pool.destroy(agent_id)
                task.status = TaskStatus.FAILED
                task.error = "New agent could not accept task"
                self._stats["failed"] += 1
                return task

        self._stats["dispatched"] += 1
        return task

    def _emit_dispatch(self, task: Task) -> None:
        self._bus.emit(
            "agents.coordinator.dispatched",
            {
                "task_id": task.task_id,
                "agent_id": task.agent_id,
                "status": task.status.name,
            },
            correlation_id=_task_correlation_id(task),
        )

    def _project_run(self, task: Task, record: RunRecord) -> None:
        if record.status is RunStatus.COMPLETED:
            task.status = TaskStatus.COMPLETED
            task.result = record.output
            task.error = None
            self._stats["completed"] += 1
            return
        if record.status is RunStatus.CANCELLED:
            task.status = TaskStatus.CANCELLED
            task.error = record.error
            return

        task.status = TaskStatus.FAILED
        task.error = record.error
        self._stats["failed"] += 1

    async def dispatch_async(
        self,
        description: str,
        task_type: str = "default",
        priority: int = 1,
        specialisation: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Dispatch a task without starting a nested event loop.

        Registered local handlers execute through ``ObservableOrchestrator``.
        Tasks with no local handler preserve the historical externally-executed
        behavior and remain ``RUNNING`` after pool assignment.
        """
        task = self._prepare_task(
            description,
            task_type=task_type,
            priority=priority,
            specialisation=specialisation,
            metadata=metadata,
        )
        if task.status is TaskStatus.FAILED:
            return task

        if task_type not in self._handlers:
            self._emit_dispatch(task)
            return task

        try:
            record = await self._orchestrator.run(
                _CoordinatorDriver(task.task_id, task_type),
                run_id=task.task_id,
                correlation_id=_task_correlation_id(task),
            )
            self._runs[task.task_id] = record
            self._project_run(task, record)
        finally:
            if task.agent_id is not None:
                self.pool.release(task.agent_id, task.task_id)

        self._emit_dispatch(task)
        return task

    def dispatch(
        self,
        description: str,
        task_type: str = "default",
        priority: int = 1,
        specialisation: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Synchronous compatibility wrapper over :meth:`dispatch_async`.

        Event-loop callers must use ``await dispatch_async(...)`` rather than
        nesting an event loop. The check occurs before task/pool mutation.
        """
        if task_type in self._handlers:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                raise RuntimeError(
                    "Coordinator.dispatch() cannot execute a registered handler "
                    "inside a running event loop; use await dispatch_async()"
                )

        if task_type not in self._handlers:
            task = self._prepare_task(
                description,
                task_type=task_type,
                priority=priority,
                specialisation=specialisation,
                metadata=metadata,
            )
            if task.status is not TaskStatus.FAILED:
                self._emit_dispatch(task)
            return task

        return asyncio.run(
            self.dispatch_async(
                description,
                task_type=task_type,
                priority=priority,
                specialisation=specialisation,
                metadata=metadata,
            )
        )

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_run_record(self, task_id: str) -> Optional[RunRecord]:
        """Return the canonical run backing a locally executed legacy task."""
        return self._runs.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [task for task in tasks if task.status == status]
        return tasks

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "pending": len(
                [task for task in self._tasks.values() if task.status == TaskStatus.PENDING]
            ),
            "running": len(
                [task for task in self._tasks.values() if task.status == TaskStatus.RUNNING]
            ),
            "completed": len(
                [task for task in self._tasks.values() if task.status == TaskStatus.COMPLETED]
            ),
            "failed": len(
                [task for task in self._tasks.values() if task.status == TaskStatus.FAILED]
            ),
            "total": len(self._tasks),
        }
