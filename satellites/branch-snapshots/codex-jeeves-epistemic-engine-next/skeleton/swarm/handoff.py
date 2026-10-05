"""A2A handoff — task envelopes for agent-to-agent delegation.

Direction-A research (frontier → production, 2026): the A2A protocol hit
150+ organizations and enterprise production within its first year. Its
core move: agents exchange *task envelopes* — a typed unit with id, input,
required capability, state machine, and artefacts — instead of raw chat
messages. This module brings the envelope pattern in-process over the
kernel bus, matching Skeleton's existing swarm vocabulary.

State machine: SUBMITTED → WORKING → (COMPLETED | FAILED | CANCELLED).
Every transition is a bus event, so the ledger and the provenance plane
see every handoff without instrumentation.

Pure domain; deterministic under an injected clock.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.errors import AgentError
from skeleton.kernel.events import EventBus


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HandoffError(AgentError):
    code = "A2A.HANDOFF"


@dataclass
class TaskEnvelope:
    """One unit of agent-to-agent work."""
    task_id: str
    capability: str
    input: Dict[str, Any]
    requester: str
    state: TaskState = TaskState.SUBMITTED
    assignee: Optional[str] = None
    artefacts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "capability": self.capability,
            "input": self.input,
            "requester": self.requester,
            "state": self.state.value,
            "assignee": self.assignee,
            "artefacts": list(self.artefacts),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class HandoffRegistry:
    """In-process A2A envelope exchange over the kernel event bus."""

    def __init__(self, *, bus: Optional[EventBus] = None,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self._bus = bus
        self._now = clock or time.time
        self._tasks: Dict[str, TaskEnvelope] = {}
        self.transitions = 0

    def _emit(self, topic: str, env: TaskEnvelope) -> None:
        if self._bus is None:
            return
        try:
            self._bus.emit(topic, env.to_dict(),
                           correlation_id=f"a2a_{env.task_id}")
        except Exception:
            pass

    def submit(self, capability: str, input: Dict[str, Any], *,
               requester: str) -> TaskEnvelope:
        now = self._now()
        env = TaskEnvelope(
            task_id=uuid.uuid4().hex[:12],
            capability=capability, input=dict(input), requester=requester,
            created_at=now, updated_at=now,
        )
        self._tasks[env.task_id] = env
        self._emit("a2a.task.submitted", env)
        return env

    def _transition(self, task_id: str, to: TaskState,
                    *, assignee: Optional[str] = None,
                    error: Optional[str] = None) -> TaskEnvelope:
        env = self._tasks.get(task_id)
        if env is None:
            raise HandoffError("unknown task", context={"task_id": task_id})
        legal = {
            TaskState.SUBMITTED: {TaskState.WORKING, TaskState.CANCELLED},
            TaskState.WORKING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
        }
        if to not in legal.get(env.state, set()):
            raise HandoffError(
                "illegal state transition",
                context={"from": env.state.value, "to": to.value},
            )
        env.state = to
        env.updated_at = self._now()
        if assignee is not None:
            env.assignee = assignee
        if error is not None:
            env.error = error
        self.transitions += 1
        self._emit(f"a2a.task.{to.value}", env)
        return env

    def accept(self, task_id: str, *, assignee: str) -> TaskEnvelope:
        return self._transition(task_id, TaskState.WORKING, assignee=assignee)

    def complete(self, task_id: str,
                 artefacts: Optional[List[Dict[str, Any]]] = None) -> TaskEnvelope:
        env = self._tasks.get(task_id)
        if env is not None and artefacts:
            env.artefacts.extend(artefacts)
        return self._transition(task_id, TaskState.COMPLETED)

    def fail(self, task_id: str, error: str) -> TaskEnvelope:
        return self._transition(task_id, TaskState.FAILED, error=error)

    def cancel(self, task_id: str) -> TaskEnvelope:
        return self._transition(task_id, TaskState.CANCELLED)

    def get(self, task_id: str) -> TaskEnvelope:
        env = self._tasks.get(task_id)
        if env is None:
            raise HandoffError("unknown task", context={"task_id": task_id})
        return env

    def open_tasks(self, capability: Optional[str] = None) -> List[TaskEnvelope]:
        out = [e for e in self._tasks.values()
               if e.state is TaskState.SUBMITTED
               and (capability is None or e.capability == capability)]
        out.sort(key=lambda e: e.created_at)
        return out

    def stats(self) -> Dict[str, Any]:
        by_state: Dict[str, int] = {}
        for e in self._tasks.values():
            by_state[e.state.value] = by_state.get(e.state.value, 0) + 1
        return {"tasks": len(self._tasks), "by_state": by_state,
                "transitions": self.transitions}
