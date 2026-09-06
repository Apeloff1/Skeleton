"""
Skeleton Agents Package

Exports:
- Coordinator: Central task coordinator
- AgentPool: Agent lifecycle management
- Task: Typed task with status tracking
- TaskStatus: Task state enum
"""

from skeleton.agents.coordination import AgentPool, Coordinator, Task, TaskStatus

__all__ = ["Coordinator", "AgentPool", "Task", "TaskStatus"]
