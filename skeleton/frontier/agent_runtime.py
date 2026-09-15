"""Provider-neutral agent runtime for promoted implementations."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol

from skeleton.frontier.contracts import (
    AgentContract,
    ProvenanceRecord,
    stable_content_digest,
)


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
    """Capability-gated execution boundary for all promoted agents.

    Optional idempotency keys provide the portable duplicate-suppression
    invariant promoted from GameForge without importing its MongoDB guard or
    durable outbox. Identical concurrent or repeated requests share one result;
    reusing a key for a different execution fails closed.
    """

    agents: dict[str, AgentLike] = field(default_factory=dict)
    idempotency_capacity: int = 4096
    _idempotency_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
        init=False,
        repr=False,
    )
    _idempotent_executions: OrderedDict[
        str, tuple[str, asyncio.Future[ExecutionResult]]
    ] = field(default_factory=OrderedDict, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.idempotency_capacity < 1:
            raise ValueError("idempotency_capacity must be positive")

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

    async def _reserve_idempotency(
        self,
        key: str,
        fingerprint: str,
    ) -> tuple[asyncio.Future[ExecutionResult], bool]:
        """Reserve an execution key or return the existing shared result future."""
        async with self._idempotency_lock:
            existing = self._idempotent_executions.get(key)
            if existing is not None:
                existing_fingerprint, future = existing
                if existing_fingerprint != fingerprint:
                    raise ValueError(
                        "idempotency key reused for a different execution payload"
                    )
                self._idempotent_executions.move_to_end(key)
                return future, False

            while len(self._idempotent_executions) >= self.idempotency_capacity:
                completed_key = next(
                    (
                        candidate_key
                        for candidate_key, (_, candidate_future) in self._idempotent_executions.items()
                        if candidate_future.done()
                    ),
                    None,
                )
                if completed_key is None:
                    raise RuntimeError(
                        "idempotency registry full — in-flight executions are backpressured"
                    )
                self._idempotent_executions.pop(completed_key, None)

            future = asyncio.get_running_loop().create_future()
            self._idempotent_executions[key] = (fingerprint, future)
            return future, True

    async def _cancel_idempotency(
        self,
        key: str,
        future: asyncio.Future[ExecutionResult],
    ) -> None:
        async with self._idempotency_lock:
            existing = self._idempotent_executions.get(key)
            if existing is not None and existing[1] is future:
                self._idempotent_executions.pop(key, None)
            if not future.done():
                future.cancel()

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
        idempotency_key: str | None = None,
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

        normalized_key: str | None = None
        shared_future: asyncio.Future[ExecutionResult] | None = None
        owns_reservation = False
        if idempotency_key is not None:
            normalized_key = idempotency_key.strip()
            if not normalized_key:
                raise ValueError("idempotency_key must not be empty")
            fingerprint = stable_content_digest(
                {
                    "agent": agent.name,
                    "task": task,
                    "context": dict(context or {}),
                    "required_capabilities": sorted(required),
                    "source_repository": source_repository,
                    "source_revision": source_revision,
                    "source_path": source_path,
                }
            )
            shared_future, owns_reservation = await self._reserve_idempotency(
                normalized_key,
                fingerprint,
            )
            if not owns_reservation:
                return await asyncio.shield(shared_future)

        provenance_metadata = {
            "agent": agent.name,
            "task": task,
            "required_capabilities": sorted(required),
            "agent_capabilities": sorted(available),
        }
        if normalized_key is not None:
            provenance_metadata["idempotency_key_sha256"] = stable_content_digest(
                normalized_key
            )

        started = datetime.now(timezone.utc)
        try:
            try:
                output = await agent.run(task, context)
            except Exception as exc:
                finished = datetime.now(timezone.utc)
                error = f"{type(exc).__name__}: {exc}"
                result = ExecutionResult(
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
            else:
                finished = datetime.now(timezone.utc)
                result = ExecutionResult(
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
        except asyncio.CancelledError:
            if normalized_key is not None and shared_future is not None:
                await self._cancel_idempotency(normalized_key, shared_future)
            raise

        if shared_future is not None and not shared_future.done():
            shared_future.set_result(result)
        return result
