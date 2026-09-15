"""Memory augmentation for the canonical Frontier agent runtime.

This layer performs retrieval composition only. Agent execution still flows
through ``AgentRuntime`` so capability checks, idempotency, lifecycle handling,
and execution provenance retain one canonical implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from skeleton.frontier.agent_runtime import AgentRuntime, ExecutionResult
from skeleton.frontier.retrieval_context import RetrieverContract


RETRIEVED_MEMORY_CONTEXT_KEY = "retrieved_memory"


@dataclass(slots=True)
class MemoryAugmentedRuntime:
    """Compose a retriever with ``AgentRuntime`` without duplicating execution."""

    runtime: AgentRuntime
    retriever: RetrieverContract

    async def execute(
        self,
        agent_name: str,
        task: str,
        *,
        context: Mapping[str, Any] | None = None,
        retrieval_query: str | None = None,
        retrieval_limit: int = 5,
        retrieval_filters: Mapping[str, Any] | None = None,
        required_capability: str | None = None,
        required_capabilities: Iterable[str] | None = None,
        source_repository: str = "Apeloff1/Skeleton",
        source_revision: str | None = None,
        source_path: str | None = None,
        idempotency_key: str | None = None,
    ) -> ExecutionResult:
        if context is not None and not isinstance(context, Mapping):
            raise TypeError("agent context must be a mapping")

        if retrieval_query is None:
            if retrieval_filters is not None:
                raise ValueError("retrieval_filters require retrieval_query")
            if retrieval_limit != 5:
                raise ValueError("retrieval_limit requires retrieval_query")
            return await self.runtime.execute(
                agent_name,
                task,
                context=context,
                required_capability=required_capability,
                required_capabilities=required_capabilities,
                source_repository=source_repository,
                source_revision=source_revision,
                source_path=source_path,
                idempotency_key=idempotency_key,
            )

        merged_context = dict(context or {})
        if RETRIEVED_MEMORY_CONTEXT_KEY in merged_context:
            raise ValueError(
                f"agent context key {RETRIEVED_MEMORY_CONTEXT_KEY!r} is reserved"
            )

        hits = await self.retriever.retrieve(
            retrieval_query,
            limit=retrieval_limit,
            filters=retrieval_filters,
        )
        merged_context[RETRIEVED_MEMORY_CONTEXT_KEY] = [
            hit.as_agent_context() for hit in hits
        ]

        return await self.runtime.execute(
            agent_name,
            task,
            context=merged_context,
            required_capability=required_capability,
            required_capabilities=required_capabilities,
            source_repository=source_repository,
            source_revision=source_revision,
            source_path=source_path,
            idempotency_key=idempotency_key,
        )
