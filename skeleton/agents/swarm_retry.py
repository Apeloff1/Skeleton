"""Retry policy primitives separating transient retry from operator replay."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.agents.swarm_runtime import SwarmTask, TaskState

@dataclass(frozen=True, slots=True)
class RetryDecision:
    retry: bool
    remaining: int
    reason: str

@dataclass(frozen=True, slots=True)
class RetryPolicy:
    retry_dead: bool = False
    retry_cancelled: bool = False
    def evaluate(self, task: SwarmTask) -> RetryDecision:
        remaining = max(0, task.max_attempts - task.attempts)
        if task.state is TaskState.CANCELLED:
            return RetryDecision(self.retry_cancelled, remaining, "cancelled")
        if task.state is TaskState.DEAD:
            return RetryDecision(self.retry_dead and remaining > 0, remaining, "dead")
        if task.state in {TaskState.SUCCEEDED, TaskState.LEASED}:
            return RetryDecision(False, remaining, task.state.value)
        return RetryDecision(remaining > 0, remaining, "retry budget available" if remaining else "retry budget exhausted")
