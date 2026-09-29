"""
Skeleton Kernel — Ids module (canonical home)
"""

from __future__ import annotations

from skeleton.kernel.primitives import BlueprintId, UserId


class AgentId(str):
    """String-compatible identity shared by agent and swarm coordination.

    Explicit names remain supported for deterministic rosters and ballots;
    generated identities use a separate namespace and a full random UUID.
    """

    @classmethod
    def new(cls) -> AgentId:
        import uuid
        return cls(f"agent-{uuid.uuid4().hex}")


class SessionId:
    """Identity primitive for Jeeves sessions."""

    @staticmethod
    def new() -> str:
        import uuid
        return f"sess-{uuid.uuid4().hex[:12]}"


class MemoryId:
    """Identity primitive for RagMemory entries."""

    @staticmethod
    def new() -> str:
        import uuid
        return f"mem-{uuid.uuid4().hex[:12]}"


class PipelineRunId:
    """Identity primitive for pipeline runs."""

    @staticmethod
    def new() -> str:
        import uuid
        return f"run-{uuid.uuid4().hex[:12]}"


__all__ = ["UserId", "BlueprintId", "AgentId", "SessionId", "MemoryId", "PipelineRunId"]
