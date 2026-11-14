"""Provider-neutral agent runtime for promoted implementations."""

from __future__ import annotations

import asyncio
import json
import math
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol

from skeleton.frontier.runtime.contracts import (
    AgentContract,
    MemoryContract,
    ProvenanceRecord,
    stable_content_digest,
)
from skeleton.frontier.runtime.retrieval_context import (
    MemoryRetriever,
    RetrieverContract,
    retrieval_audit_summary,
)


_RETRIEVED_CONTEXT_KEY = "retrieved_context"


class AgentFailure(RuntimeError):
    """Raised when an agent cannot complete a task."""


def _public_agent_failure(error: BaseException) -> str:
    """Return stable diagnostics without exposing arbitrary exception text."""
    return f"AgentFailure: agent execution failed with {type(error).__name__}"


class AgentLike(AgentContract, Protocol):
    async def run(self, task: str, context: Mapping[str, Any] | None = None) -> Any: ...


def _require_normalized_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _optional_normalized_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_normalized_text(value, field_name)


def _normalize_capabilities(
    capabilities: Iterable[str],
    *,
    field_name: str = "capabilities",
) -> frozenset[str]:
    if isinstance(capabilities, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings, not a string")

    normalized: set[str] = set()
    try:
        iterator = iter(capabilities)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of strings") from exc

    for capability in iterator:
        if not isinstance(capability, str):
            raise TypeError(f"{field_name} entries must be strings")
        value = capability.strip().lower()
        if not value:
            raise ValueError(f"{field_name} entries must not be empty")
        normalized.add(value)
    return frozenset(normalized)


def _canonical_idempotency_value(value: object, *, path: str) -> Any:
    """Detach strict JSON identity before reservation or agent side effects.

    Bounded traversal prevents recursive, excessively deep or very large
    requests from turning fingerprinting into an unbounded resource sink.
    """
    remaining_nodes = 100_000
    remaining_bytes = 8_388_608
    active: set[int] = set()

    def visit(item: object, depth: int) -> Any:
        nonlocal remaining_nodes, remaining_bytes
        remaining_nodes -= 1
        if remaining_nodes < 0 or depth > 64:
            raise ValueError(f"{path} exceeds structural identity budget")
        if item is None or type(item) is bool:
            return item
        if type(item) is str:
            if len(item) > 1_048_576:
                raise ValueError(f"{path} exceeds text identity budget")
            try:
                remaining_bytes -= len(item.encode("utf-8"))
            except UnicodeError as exc:
                raise ValueError(f"{path} contains invalid Unicode") from exc
            if remaining_bytes < 0:
                raise ValueError(f"{path} exceeds text identity budget")
            return item
        if type(item) is int:
            if item.bit_length() > 4096:
                raise ValueError(f"{path} exceeds integer identity budget")
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError(f"{path} must contain only finite JSON numbers")
            return item
        if isinstance(item, (list, Mapping)):
            identity = id(item)
            if identity in active:
                raise ValueError(f"{path} must not contain recursive containers")
            if len(item) > remaining_nodes:
                raise ValueError(f"{path} exceeds structural identity budget")
            active.add(identity)
            try:
                if isinstance(item, list):
                    return [visit(child, depth + 1) for child in item]
                canonical: dict[str, Any] = {}
                for key, child in item.items():
                    if type(key) is not str:
                        raise TypeError(f"{path} JSON object keys must be strings")
                    normalized_key = visit(key, depth + 1)
                    if normalized_key in canonical:
                        raise ValueError(f"{path} contains duplicate JSON object keys")
                    canonical[normalized_key] = visit(child, depth + 1)
                return canonical
            finally:
                active.remove(identity)
        raise TypeError(f"{path} must contain only JSON-compatible values")

    canonical = visit(value, 0)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > 8_388_608:
        raise ValueError(f"{path} exceeds encoded identity budget")
    return canonical


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

    Runtime retrieval consumes the canonical ``RetrieverContract``. The
    ``memory`` field remains a compatibility constructor alias from the initial
    #448 integration and is normalized to ``MemoryRetriever`` during
    initialization. Validated hits are injected under ``retrieved_context`` and
    their content-free identities are retained in execution provenance.
    """

    agents: dict[str, AgentLike] = field(default_factory=dict)
    idempotency_capacity: int = 4096
    memory: MemoryContract | None = None
    retriever: RetrieverContract | None = None
    max_idempotency_waiters: int = 128
    _waiter_counts: dict[asyncio.Future[ExecutionResult], int] = field(default_factory=dict, init=False, repr=False)
    _idempotency_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
        init=False,
        repr=False,
    )
    _idempotent_executions: OrderedDict[
        str, tuple[str, asyncio.Future[ExecutionResult]]
    ] = field(default_factory=OrderedDict, init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.idempotency_capacity, bool) or not isinstance(
            self.idempotency_capacity, int
        ):
            raise TypeError("idempotency_capacity must be an integer")
        if not 1 <= self.idempotency_capacity <= 65_536:
            raise ValueError("idempotency_capacity must be in [1, 65536]")
        if type(self.max_idempotency_waiters) is not int or not 1 <= self.max_idempotency_waiters <= 4096:
            raise ValueError("max_idempotency_waiters must be in [1, 4096]")
        if self.memory is not None and self.retriever is not None:
            raise ValueError("configure either memory or retriever, not both")
        if self.retriever is None and self.memory is not None:
            self.retriever = MemoryRetriever(self.memory)

    def register(self, agent: AgentLike) -> None:
        name = _require_normalized_text(getattr(agent, "name", None), "agent name")
        capabilities = getattr(agent, "capabilities", None)
        if capabilities is None:
            raise TypeError("agent capabilities must be an iterable of strings")
        _normalize_capabilities(capabilities, field_name="agent capabilities")
        if name in self.agents:
            raise ValueError(f"agent already registered: {name}")
        self.agents[name] = agent

    def resolve(self, name: str) -> AgentLike:
        normalized_name = _require_normalized_text(name, "agent name")
        try:
            return self.agents[normalized_name]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {normalized_name}") from exc

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
                count = self._waiter_counts.get(future, 0)
                if count >= self.max_idempotency_waiters:
                    raise RuntimeError("idempotency waiter capacity exceeded")
                self._waiter_counts[future] = count + 1
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
        memory_query: str | None = None,
        memory_limit: int = 5,
        memory_filters: Mapping[str, Any] | None = None,
    ) -> ExecutionResult:
        normalized_agent_name = _require_normalized_text(agent_name, "agent name")
        normalized_task = _require_normalized_text(task, "task")
        normalized_source_repository = _require_normalized_text(
            source_repository,
            "source_repository",
        )
        normalized_source_revision = _optional_normalized_text(
            source_revision,
            "source_revision",
        )
        normalized_source_path = _optional_normalized_text(source_path, "source_path")
        if context is not None and not isinstance(context, Mapping):
            raise TypeError("context must be a mapping")
        normalized_context = _canonical_idempotency_value(
            context if context is not None else {}, path="context"
        )

        normalized_memory_query: str | None = None
        canonical_memory_filters: dict[str, Any] | None = None
        if memory_query is not None:
            normalized_memory_query = _require_normalized_text(
                memory_query,
                "memory_query",
            )
            if isinstance(memory_limit, bool) or not isinstance(memory_limit, int):
                raise TypeError("memory_limit must be an integer")
            if memory_limit < 1:
                raise ValueError("memory_limit must be positive")
            if memory_filters is not None and not isinstance(memory_filters, Mapping):
                raise TypeError("memory_filters must be a mapping")
            if _RETRIEVED_CONTEXT_KEY in normalized_context:
                raise ValueError(
                    f"context key {_RETRIEVED_CONTEXT_KEY!r} is reserved for runtime retrieval"
                )
            canonical_filters = _canonical_idempotency_value(
                dict(memory_filters or {}),
                path="memory_filters",
            )
            if not isinstance(canonical_filters, dict):
                raise TypeError("memory_filters must normalize to an object")
            canonical_memory_filters = canonical_filters
        elif memory_filters is not None:
            raise ValueError("memory_filters requires memory_query")

        agent = self.resolve(normalized_agent_name)

        required_source = (
            required_capabilities if required_capabilities is not None else ()
        )
        required = set(
            _normalize_capabilities(
                required_source,
                field_name="required_capabilities",
            )
        )
        if required_capability is not None:
            required.update(
                _normalize_capabilities(
                    (required_capability,),
                    field_name="required_capability",
                )
            )
        available = _normalize_capabilities(
            agent.capabilities,
            field_name="agent capabilities",
        )
        missing = sorted(required.difference(available))
        if missing:
            raise PermissionError(
                f"agent {agent.name!r} lacks capabilities: {', '.join(missing)}"
            )

        normalized_key: str | None = None
        shared_future: asyncio.Future[ExecutionResult] | None = None
        owns_reservation = False
        if idempotency_key is not None:
            normalized_key = _require_normalized_text(
                idempotency_key,
                "idempotency_key",
            )
            if len(normalized_key) > 256:
                raise ValueError("idempotency_key exceeds 256 characters")
            canonical_context = _canonical_idempotency_value(
                normalized_context,
                path="context",
            )
            # Dispatch the detached fingerprinted context, not caller aliases.
            normalized_context = canonical_context
            fingerprint = stable_content_digest(
                {
                    "agent": agent.name,
                    "task": normalized_task,
                    "context": canonical_context,
                    "required_capabilities": sorted(required),
                    "source_repository": normalized_source_repository,
                    "source_revision": normalized_source_revision,
                    "source_path": normalized_source_path,
                    "memory_query": normalized_memory_query,
                    "memory_limit": memory_limit if normalized_memory_query is not None else None,
                    "memory_filters": canonical_memory_filters,
                }
            )
            shared_future, owns_reservation = await self._reserve_idempotency(
                normalized_key,
                fingerprint,
            )
            if not owns_reservation:
                try:
                    return deepcopy(await asyncio.shield(shared_future))
                finally:
                    count = self._waiter_counts.get(shared_future, 0)
                    if count <= 1:
                        self._waiter_counts.pop(shared_future, None)
                    else:
                        self._waiter_counts[shared_future] = count - 1

        provenance_metadata: dict[str, Any] = {
            "agent": agent.name,
            "task": normalized_task,
            "required_capabilities": sorted(required),
            "agent_capabilities": sorted(available),
        }
        if normalized_key is not None:
            provenance_metadata["idempotency_key_sha256"] = stable_content_digest(
                normalized_key
            )
        if normalized_memory_query is not None:
            provenance_metadata["retrieval_request"] = {
                "query_sha256": stable_content_digest(normalized_memory_query),
                "limit": memory_limit,
                "filters_sha256": stable_content_digest(canonical_memory_filters or {}),
            }

        started = datetime.now(timezone.utc)
        try:
            try:
                execution_context = normalized_context
                if normalized_memory_query is not None:
                    if self.retriever is None:
                        raise RuntimeError(
                            "memory_query requires a configured canonical RetrieverContract"
                        )
                    hits = await self.retriever.retrieve(
                        normalized_memory_query,
                        limit=memory_limit,
                        filters=canonical_memory_filters,
                    )
                    execution_context = dict(normalized_context)
                    execution_context[_RETRIEVED_CONTEXT_KEY] = [
                        hit.as_agent_context() for hit in hits
                    ]
                    provenance_metadata["retrieval_hits"] = retrieval_audit_summary(hits)

                output = await agent.run(normalized_task, execution_context)
                if shared_future is not None:
                    # Bound and detach replayable output before computing provenance.
                    # Invalid results become terminal failures, not automatic retries.
                    if type(output) is bytes:
                        if len(output) > 8_388_608:
                            raise ValueError("agent output byte budget exceeded")
                    else:
                        output = _canonical_idempotency_value(output, path="output")
            except Exception as exc:
                finished = datetime.now(timezone.utc)
                error = _public_agent_failure(exc)
                result = ExecutionResult(
                    task=normalized_task,
                    agent=agent.name,
                    started_at=started,
                    finished_at=finished,
                    error=error,
                    provenance=ProvenanceRecord.for_artifact(
                        source_repository=normalized_source_repository,
                        source_revision=normalized_source_revision,
                        source_path=normalized_source_path,
                        payload={
                            "task": normalized_task,
                            "agent": agent.name,
                            "error": error,
                        },
                        operation="agent.execute.failed",
                        metadata=provenance_metadata,
                    ),
                )
            else:
                finished = datetime.now(timezone.utc)
                result = ExecutionResult(
                    task=normalized_task,
                    agent=agent.name,
                    started_at=started,
                    finished_at=finished,
                    output=output,
                    provenance=ProvenanceRecord.for_artifact(
                        source_repository=normalized_source_repository,
                        source_revision=normalized_source_revision,
                        source_path=normalized_source_path,
                        payload=output,
                        operation="agent.execute.completed",
                        metadata=provenance_metadata,
                    ),
                )

            if shared_future is not None and not shared_future.done():
                shared_future.set_result(deepcopy(result))
            return result
        except BaseException:
            if normalized_key is not None and shared_future is not None:
                await self._cancel_idempotency(normalized_key, shared_future)
            raise
