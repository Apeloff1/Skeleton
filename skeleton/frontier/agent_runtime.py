"""Provider-neutral agent runtime for promoted implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol

from skeleton.frontier.contracts import AgentContract, ProvenanceRecord


class AgentFailure(RuntimeError):
    """Raised when an agent cannot complete a task."""


class AgentLike(AgentContract, Protocol):
    async def run(self, task: str, context: Mapping[str, Any] | None = None) -> Any: ...


def _normalize_capabilities(capabilities: Iterable[str]) -> frozenset[str]:
    return frozenset(
        capability.strip().lower()
        for capability in capabilities
        if capability and capability.strip()
    )


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
    """Capability-gated execution boundary for all promoted agents."""

    agents: dict[str, AgentLike] = field(default_factory=dict)

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
        required_capabilities: Iterable[str] | None = None,
        source_repository: str = "Apeloff1/Skeleton",
        source_revision: str | None = None,
        source_path: str | None = None,
    ) -> ExecutionResult:
        if not task.strip():
            raise ValueError("task must not be empty")
        agent = self.resolve(agent_name)

        required = set(_normalize_capabilities(required_capabilities or ()))
        if required_capability:
            required.update(_normalize_capabilities((required_capability,)))
        available = _normalize_capabilities(agent.capabilities)
        missing = sorted(required.difference(available))
        if missing:
            raise PermissionError(
                f"agent {agent.name!r} lacks capabilities: {', '.join(missing)}"
            )

        provenance_metadata = {
            "agent": agent.name,
            "task": task,
            "required_capabilities": sorted(required),
            "agent_capabilities": sorted(available),
        }
        started = datetime.now(timezone.utc)
        try:
            output = await agent.run(task, context)
        except Exception as exc:
            finished = datetime.now(timezone.utc)
            error = f"{type(exc).__name__}: {exc}"
            return ExecutionResult(
                task=task,
                agent=agent.name,
                started_at=started,
                finished_at=finished,
                error=error,
                provenance=ProvenanceRecord.for_artifact(
                    source_repository=source_repository,
                    source_revision=source_revision,
                    source_path=source_path,
                    payload={"task": task, "agent": agent.name, "error": error},
                    operation="agent.execute.failed",
                    metadata=provenance_metadata,
                ),
            )

        finished = datetime.now(timezone.utc)
        return ExecutionResult(
            task=task,
            agent=agent.name,
            started_at=started,
            finished_at=finished,
            output=output,
            provenance=ProvenanceRecord.for_artifact(
                source_repository=source_repository,
                source_revision=source_revision,
                source_path=source_path,
                payload=output,
                operation="agent.execute.completed",
                metadata=provenance_metadata,
            ),
        )
