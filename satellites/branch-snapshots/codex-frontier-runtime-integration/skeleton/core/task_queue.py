"""Task queue — durable priority work queue with workers and retries.

Named queues with priority levels, visibility timeouts, dead-letter
handling, and at-least-once delivery. Workers pull tasks, ack on
success, nack for retry, and poison tasks dead-letter after the
retry budget is exhausted.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Task:
    task_id: str
    queue: str
    payload: Dict[str, Any]
    priority: int = 0
    attempts: int = 0
    max_attempts: int = 3
    enqueued_ns: int = 0
    visible_at_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "queue": self.queue,
            "priority": self.priority,
            "attempts": self.attempts,
            "payload": self.payload,
        }


class TaskQueue:
    """Priority task queue with dead-letter support."""

    def __init__(self, visibility_timeout_s: float = 30.0):
        self.visibility_timeout_s = visibility_timeout_s
        self._queues: Dict[str, List[Task]] = {}
        self._in_flight: Dict[str, Task] = {}
        self._dead_letter: Dict[str, List[Task]] = {}
        self._completed = 0

    def enqueue(self, queue: str, payload: Dict[str, Any],
                priority: int = 0, max_attempts: int = 3,
                delay_s: float = 0.0) -> Task:
        task = Task(
            task_id=uuid.uuid4().hex[:12],
            queue=queue,
            payload=payload,
            priority=priority,
            max_attempts=max_attempts,
            enqueued_ns=time.time_ns(),
            visible_at_ns=time.time_ns() + int(delay_s * 1e9),
        )
        self._queues.setdefault(queue, []).append(task)
        return task

    def _requeue_expired(self, queue: str) -> None:
        now = time.time_ns()
        expired = []
        for tid, task in list(self._in_flight.items()):
            if task.queue == queue and task.visible_at_ns < now:
                expired.append(tid)
        for tid in expired:
            task = self._in_flight.pop(tid)
            if task.attempts >= task.max_attempts:
                self._dead_letter.setdefault(queue, []).append(task)
            else:
                task.visible_at_ns = now
                self._queues[queue].append(task)

    def dequeue(self, queue: str) -> Optional[Task]:
        self._queues.setdefault(queue, [])
        self._requeue_expired(queue)
        now = time.time_ns()
        ready = [t for t in self._queues[queue] if t.visible_at_ns <= now]
        if not ready:
            return None
        ready.sort(key=lambda t: (-t.priority, t.enqueued_ns))
        task = ready[0]
        self._queues[queue].remove(task)
        task.attempts += 1
        task.visible_at_ns = now + int(self.visibility_timeout_s * 1e9)
        self._in_flight[task.task_id] = task
        return task

    def ack(self, task_id: str) -> bool:
        if task_id in self._in_flight:
            del self._in_flight[task_id]
            self._completed += 1
            return True
        return False

    def nack(self, task_id: str, requeue: bool = True) -> bool:
        task = self._in_flight.pop(task_id, None)
        if not task:
            return False
        if requeue and task.attempts < task.max_attempts:
            task.visible_at_ns = time.time_ns()
            self._queues[task.queue].append(task)
        else:
            self._dead_letter.setdefault(task.queue, []).append(task)
        return True

    def depth(self, queue: str) -> int:
        return len(self._queues.get(queue, []))

    def dead_letters(self, queue: str) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._dead_letter.get(queue, [])]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "task-queue-card",
            "queues": {q: {"depth": len(tasks), "dead": len(self._dead_letter.get(q, []))} for q, tasks in self._queues.items()},
            "in_flight": len(self._in_flight),
            "completed": self._completed,
        }
