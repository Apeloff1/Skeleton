"""Explicit long-running task state for MCP-style AI shell operations.

The task record is orchestration metadata only. It does not create a background
worker and does not execute a process.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import threading
import time
from typing import Callable


class MCPTaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class MCPTask:
    task_id: str
    request_id: str
    principal: str
    tool: str
    state: MCPTaskState
    created_at: float
    updated_at: float
    progress: float = 0.0
    message: str = ""
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError("MCP task progress out of range")
        if len(self.message) > 2048:
            raise ValueError("MCP task message too long")

    def to_dict(self) -> dict[str, object]:
        return {
            "taskId": self.task_id,
            "requestId": self.request_id,
            "principal": self.principal,
            "tool": self.tool,
            "state": self.state.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "progress": self.progress,
            "message": self.message,
            "correlationId": self.correlation_id,
        }


_TERMINAL = {
    MCPTaskState.SUCCEEDED,
    MCPTaskState.FAILED,
    MCPTaskState.CANCELLED,
}


class MCPTaskRegistry:
    def __init__(
        self,
        *,
        max_tasks: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_tasks <= 0:
            raise ValueError("max_tasks must be positive")
        self.max_tasks = max_tasks
        self._clock = clock
        self._serial = 0
        self._items: dict[str, MCPTask] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        request_id: str,
        principal: str,
        tool: str,
        correlation_id: str = "",
    ) -> MCPTask:
        with self._lock:
            if len(self._items) >= self.max_tasks:
                raise RuntimeError("MCP task capacity exhausted")
            self._serial += 1
            now = self._clock()
            raw = f"{request_id}:{principal}:{tool}:{self._serial}:{now}"
            task_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
            task = MCPTask(
                task_id,
                request_id,
                principal,
                tool,
                MCPTaskState.PENDING,
                now,
                now,
                0.0,
                "",
                correlation_id,
            )
            self._items[task_id] = task
            return task

    def update(
        self,
        task_id: str,
        *,
        state: MCPTaskState | None = None,
        progress: float | None = None,
        message: str | None = None,
    ) -> MCPTask:
        with self._lock:
            current = self._items[task_id]
            if current.state in _TERMINAL:
                raise RuntimeError("terminal MCP task cannot be updated")
            next_state = current.state if state is None else MCPTaskState(state)
            next_progress = current.progress if progress is None else progress
            next_message = current.message if message is None else message
            if current.state is MCPTaskState.PENDING and next_state not in {
                MCPTaskState.PENDING,
                MCPTaskState.RUNNING,
                MCPTaskState.CANCELLED,
                MCPTaskState.FAILED,
            }:
                raise RuntimeError("invalid MCP task transition")
            if current.state is MCPTaskState.RUNNING and next_state not in {
                MCPTaskState.RUNNING,
                MCPTaskState.SUCCEEDED,
                MCPTaskState.FAILED,
                MCPTaskState.CANCELLED,
            }:
                raise RuntimeError("invalid MCP task transition")
            if next_state is MCPTaskState.SUCCEEDED:
                next_progress = 1.0
            updated = MCPTask(
                current.task_id,
                current.request_id,
                current.principal,
                current.tool,
                next_state,
                current.created_at,
                self._clock(),
                next_progress,
                next_message,
                current.correlation_id,
            )
            self._items[task_id] = updated
            return updated

    def get(self, task_id: str) -> MCPTask:
        with self._lock:
            return self._items[task_id]

    def snapshot(self) -> tuple[MCPTask, ...]:
        with self._lock:
            return tuple(self._items[key] for key in sorted(self._items))
