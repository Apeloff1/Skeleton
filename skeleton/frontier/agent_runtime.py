"""Provider-neutral, bounded asynchronous agent execution.

One runtime belongs to one event loop while work is pending. Adapters must be
cooperative async functions; blocking CPU work belongs in a managed worker.
Capability checks restrict dispatch, and do not sandbox arbitrary adapter code.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import uuid4

from skeleton.frontier.capabilities import CapabilityPolicy, capability_names
from skeleton.frontier.contracts import AgentContract, ProvenanceRecord
from skeleton.frontier.execution import (
    ExecutionPolicy, ExecutionStatus, RuntimeBusy, RuntimeClosed, TransientAgentError, positive_seconds,
)
from skeleton.frontier.health import HealthState
from skeleton.frontier.payloads import json_snapshot
from skeleton.frontier.singleflight import SingleFlight


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
    request_id: str = ""
    status: ExecutionStatus = ExecutionStatus.COMPLETED
    attempts: int = 1
    elapsed_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.status is ExecutionStatus.COMPLETED

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id, "task": self.task, "agent": self.agent,
            "status": self.status.value, "succeeded": self.succeeded,
            "started_at": self.started_at.isoformat(), "finished_at": self.finished_at.isoformat(),
            "output": self.output, "error": self.error, "attempts": self.attempts,
            "elapsed_ms": self.elapsed_ms,
            "provenance": self.provenance.as_dict() if self.provenance else None,
        }


class AgentRuntime:
    """Execute registered adapters within explicit capabilities and budgets."""

    def __init__(self, agents: Mapping[str, AgentLike] | None = None,
                 policy: CapabilityPolicy | None = None,
                 health: HealthState = HealthState.HEALTHY,
                 *, execution_policy: ExecutionPolicy | None = None) -> None:
        self.policy = policy if policy is not None else CapabilityPolicy.from_names(())
        self.health = health
        self._execution_policy = execution_policy or ExecutionPolicy()
        if not isinstance(self.policy, CapabilityPolicy) or not isinstance(self.health, HealthState):
            raise TypeError("policy and health must use the frontier contracts")
        if not isinstance(self.execution_policy, ExecutionPolicy):
            raise TypeError("execution_policy must be ExecutionPolicy")
        self._agents: dict[str, AgentLike] = {}
        self._capabilities: dict[str, frozenset[str]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._pending = self._active = 0
        self._tasks: dict[asyncio.Task, int] = {}
        self._closed = False
        self._singleflight = SingleFlight(max_inflight=self.execution_policy.max_concurrency + self.execution_policy.max_queue)
        self._counts = {"completed": 0, "failed": 0, "timed_out": 0, "cancelled": 0, "rejected": 0, "retries": 0}
        for name, agent in (agents or {}).items():
            if name != agent.name:
                raise ValueError("agent registry key must match agent.name")
            self.register(agent)

    @property
    def execution_policy(self) -> ExecutionPolicy:
        return self._execution_policy

    @property
    def agents(self) -> Mapping[str, AgentLike]:
        return MappingProxyType(self._agents)

    def register(self, agent: AgentLike) -> None:
        if self._closed:
            raise RuntimeClosed("agent runtime is closed")
        if not isinstance(agent.name, str) or not agent.name.strip() or agent.name != agent.name.strip():
            raise ValueError("agent name must be non-empty and have no surrounding whitespace")
        if not inspect.iscoroutinefunction(agent.run):
            raise TypeError("agent.run must be an async function")
        if agent.name in self._agents:
            raise ValueError(f"agent already registered: {agent.name}")
        if len(self._agents) >= 256:
            raise RuntimeBusy("agent registry capacity reached")
        capabilities = capability_names(agent.capabilities)
        self._agents[agent.name] = agent
        self._capabilities[agent.name] = capabilities

    def resolve(self, name: str) -> AgentLike:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {name}") from exc

    def _authorize(self, agent_name: str, required_capability: str | None,
                   *, admitted: bool = False) -> AgentLike:
        if self._closed and not admitted:
            raise RuntimeClosed("agent runtime is closed")
        if not isinstance(self.health, HealthState) or self.health is HealthState.UNAVAILABLE:
            raise RuntimeError("agent runtime unavailable")
        agent = self.resolve(agent_name)
        capabilities = self._capabilities[agent_name]
        if agent.name != agent_name or capability_names(agent.capabilities) != capabilities:
            raise ValueError("registered agent identity or capabilities changed")
        if required_capability is not None:
            required = capability_names((required_capability,))
            if not required.issubset(capabilities):
                raise PermissionError(f"agent {agent_name!r} lacks capability {required_capability!r}")
        # Omitting a requested capability must never bypass the policy. An
        # adapter may use every capability it declares during a single call.
        self.policy.require(capabilities)
        return agent

    def stats(self) -> dict[str, Any]:
        return {**self._counts, "registered": len(self._agents), "active": self._active,
                "queued": self._pending - self._active, "closed": self._closed,
                "idempotency": self._singleflight.stats()}

    async def aclose(self, *, grace_period: float = 5.0) -> None:
        """Stop admissions, drain accepted work, then cancel cooperative stragglers."""
        positive_seconds("grace_period", grace_period)
        if asyncio.current_task() in self._tasks:
            raise RuntimeError("an executing agent cannot shut down its own runtime")
        if self._pending and asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("shutdown must run on the runtime's event loop")
        self._closed = True
        pending = set(self._tasks) | set(self._singleflight.tasks)
        if not pending:
            return
        try:
            _, pending = await asyncio.wait(pending, timeout=grace_period)
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def __aenter__(self) -> AgentRuntime:
        if self._closed:
            raise RuntimeClosed("agent runtime is closed")
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.aclose()

    async def execute(self, agent_name: str, task: str, *,
                      context: Mapping[str, Any] | None = None,
                      required_capability: str | None = None,
                      source_repository: str = "Apeloff1/Skeleton",
                      request_id: str | None = None,
                      timeout: float | None = None,
                      idempotency_key: str | None = None) -> ExecutionResult:
        kwargs = dict(context=context, required_capability=required_capability,
                      source_repository=source_repository, request_id=request_id, timeout=timeout)
        if idempotency_key is None:
            return await self._execute(agent_name, task, **kwargs)
        self._authorize(agent_name, required_capability)
        payload = json_snapshot({"agent": agent_name, "task": task, "context": dict(context or {}),
                                 "required_capability": required_capability,
                                 "source_repository": source_repository, "timeout": timeout},
                                max_bytes=self.execution_policy.max_payload_bytes)
        kwargs["context"] = payload["context"]
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return await self._singleflight.run(idempotency_key, fingerprint,
                                            lambda: self._execute(agent_name, task, **kwargs),
                                            cacheable=lambda result: result.succeeded)

    async def _execute(self, agent_name: str, task: str, *,
                      context: Mapping[str, Any] | None = None,
                      required_capability: str | None = None,
                      source_repository: str = "Apeloff1/Skeleton",
                      request_id: str | None = None,
                      timeout: float | None = None) -> ExecutionResult:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must not be empty")
        task_digest = hashlib.sha256(task.encode("utf-8")).hexdigest()
        if not isinstance(source_repository, str) or not source_repository.strip() or len(source_repository) > 256:
            raise ValueError("source_repository must contain 1 to 256 characters")
        if context is not None and not isinstance(context, Mapping):
            raise ValueError("context must be a mapping")
        if request_id is None:
            request_id = uuid4().hex
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
            raise ValueError("request_id must contain 1 to 128 characters")
        limits = self.execution_policy
        timeout = limits.execution_timeout if timeout is None else min(
            positive_seconds("timeout", timeout), limits.execution_timeout)
        snapshot = json_snapshot({"task": task, "context": dict(context or {})},
                                 max_bytes=limits.max_payload_bytes)
        self._authorize(agent_name, required_capability)
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            if self._pending:
                raise RuntimeError("runtime already has work on another event loop")
            self._loop = loop
            self._semaphore = asyncio.Semaphore(limits.max_concurrency)
        if self._pending >= limits.max_concurrency + limits.max_queue:
            self._counts["rejected"] += 1
            raise RuntimeBusy("agent runtime admission queue is full")
        caller = asyncio.current_task()
        self._pending += 1
        self._tasks[caller] = self._tasks.get(caller, 0) + 1
        acquired = False
        try:
            try:
                async with asyncio.timeout(limits.queue_timeout):
                    await self._semaphore.acquire()
            except TimeoutError as exc:
                self._counts["rejected"] += 1
                raise RuntimeBusy("agent runtime queue deadline expired") from exc
            acquired = True
            self._active += 1
            agent = self._authorize(agent_name, required_capability, admitted=True)
            started = datetime.now(timezone.utc)
            tick = loop.time()
            output = error = None
            status = ExecutionStatus.COMPLETED
            attempts = 0
            try:
                async with asyncio.timeout(timeout) as deadline:
                    while attempts < limits.max_attempts:
                        attempts += 1
                        try:
                            attempt_context = json_snapshot(snapshot["context"], max_bytes=limits.max_payload_bytes)
                            output = await agent.run(task, attempt_context)
                            output = json_snapshot(output, max_bytes=limits.max_payload_bytes)
                        except TransientAgentError as exc:
                            if attempts < limits.max_attempts:
                                self._counts["retries"] += 1
                                await asyncio.sleep(limits.backoff(attempts))
                                self._authorize(agent_name, required_capability, admitted=True)
                                continue
                            error = f"agent execution failed ({type(exc).__name__})"
                            status = ExecutionStatus.FAILED
                        except Exception as exc:
                            error = f"agent execution failed ({type(exc).__name__})"
                            status = ExecutionStatus.FAILED
                        break
                if deadline.expired():
                    raise TimeoutError
            except TimeoutError:
                output = None
                error = "agent execution deadline expired"
                status = ExecutionStatus.TIMED_OUT
            if status is not ExecutionStatus.COMPLETED:
                output = None
            self._counts[status.value] += 1
            return ExecutionResult(
                task=task, agent=agent_name, started_at=started,
                finished_at=datetime.now(timezone.utc), output=output, error=error,
                request_id=request_id, status=status, attempts=attempts, elapsed_ms=(loop.time() - tick) * 1000,
                provenance=ProvenanceRecord(
                    source_repository=source_repository, operation=f"agent.execute.{status.value}",
                    metadata={"agent": agent_name, "request_id": request_id,
                              "task_sha256": task_digest},
                ),
            )
        except asyncio.CancelledError:
            self._counts["cancelled"] += 1
            raise
        finally:
            if acquired:
                self._active -= 1
                self._semaphore.release()
            self._pending -= 1
            self._tasks[caller] -= 1
            if self._tasks[caller] == 0:
                del self._tasks[caller]
