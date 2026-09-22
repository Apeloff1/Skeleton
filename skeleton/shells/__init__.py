"""Bounded shell execution core.

This landing slice exposes the stable argv-only execution boundary plus the
queue/worker lifecycle primitives needed by higher shell layers.
"""

from skeleton.shells.executor import ExecutionOutcome, ExecutorConfig, ShellExecutor
from skeleton.shells.queue import QueueItem, QueueState, ShellWorkQueue
from skeleton.shells.runner import (
    ShellCommand,
    ShellExecutionError,
    ShellPolicy,
    ShellPolicyError,
    ShellResult,
    ShellRunner,
)
from skeleton.shells.worker import (
    DrainReport,
    QueueWorker,
    WorkDisposition,
    WorkResult,
    WorkerCounters,
    WorkerGroup,
    WorkerGroupSnapshot,
    WorkerPolicy,
    WorkerSnapshot,
    WorkerState,
)

__all__ = [
    "DrainReport",
    "ExecutionOutcome",
    "ExecutorConfig",
    "QueueItem",
    "QueueState",
    "QueueWorker",
    "ShellCommand",
    "ShellExecutionError",
    "ShellExecutor",
    "ShellPolicy",
    "ShellPolicyError",
    "ShellResult",
    "ShellRunner",
    "ShellWorkQueue",
    "WorkDisposition",
    "WorkResult",
    "WorkerCounters",
    "WorkerGroup",
    "WorkerGroupSnapshot",
    "WorkerPolicy",
    "WorkerSnapshot",
    "WorkerState",
]
