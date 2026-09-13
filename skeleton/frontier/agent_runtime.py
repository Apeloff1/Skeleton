"""Provider-neutral agent runtime for promoted implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from skeleton.frontier.capabilities import CapabilityPolicy
from skeleton.frontier.contracts import AgentContract, ProvenanceRecord
from skeleton.frontier.health import HealthState


class AgentFailure(RuntimeError):
    """Raised when an agent cannot complete a task."""


class AgentLike(AgentContract, Protocol):
    async def run(self, task: str, context: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    task: str
    agent: str
    started_at: datetime
    finished_at: datetime
    output: Any = None
    error: str | None = None
    provenance: ProvenanceRecord | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(slots=True)
class AgentRuntime:
    """Capability- and health-gated execution boundary for promoted agents."""

    agents: dict[str, AgentLike] = field(default_factory=dict)
    policy: CapabilityPolicy = field(default_factory=lambda: CapabilityPolicy.from_names(()))
    health: HealthState = HealthState.HEALTHY

    def register(self, agent: AgentLike) -> None:
        if not agent.name.strip():
            raise ValueError("agent name must not be empty")
        if agent.name in self.agents:
            raise ValueError(f"agent already registered: {agent.name}")
        self.agents[agent.name] = agent

    def resolve(self, name: str) -> AgentLike:
        try:
            return self.agents[name]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {name}") from exc

    async def execute(
        self,
        agent_name: str,
        task: str,
        *,
        context: Mapping[str, Any] | None = None,
        required_capability: str | None = None,
        source_repository: str = "Apeloff1/Skeleton",
    ) -> ExecutionResult:
        if not task.strip():
            raise ValueError("task must not be empty")
        if self.health is HealthState.UNAVAILABLE:
            raise RuntimeError("agent runtime unavailable")
        agent = self.resolve(agent_name)
        if required_capability:
            self.policy.require((required_capability,))
            if required_capability not in agent.capabilities:
                raise PermissionError(
                    f"agent {agent.name!r} lacks capability {required_capability!r}"
                )

        started = datetime.now(timezone.utc)
        try:
            output = await agent.run(task, context)
        except Exception as exc:
            finished = datetime.now(timezone.utc)
            return ExecutionResult(
                task=task,
                agent=agent.name,
                started_at=started,
                finished_at=finished,
                error=f"{type(exc).__name__}: {exc}",
                provenance=ProvenanceRecord(
                    source_repository=source_repository,
                    operation="agent.execute.failed",
                    metadata={"agent": agent.name, "task": task},
                ),
            )

        finished = datetime.now(timezone.utc)
        return ExecutionResult(
            task=task,
            agent=agent.name,
            started_at=started,
            finished_at=finished,
            output=output,
            provenance=ProvenanceRecord(
                source_repository=source_repository,
                operation="agent.execute.completed",
                metadata={"agent": agent.name, "task": task},
            ),
        )
