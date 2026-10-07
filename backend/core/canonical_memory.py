"""Production canonical Mongo memory authority.

The backend owns the Mongo transport, while the Skeleton engine owns resource
admission and lifecycle governance. This module binds those two process
boundaries without creating a second quota or governance registry.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.databases import core_db
from core.engine_client import EngineClient
from skeleton.contracts.memory_record import MemoryRecord, MemoryWriteProposal
from skeleton.memory.writeback import AsyncGovernedMemoryWriter
from skeleton.persistence.memory_repository import MongoMemoryRepository


class CanonicalMemoryUnavailable(RuntimeError):
    """Canonical memory writes cannot proceed without the engine boundary."""


def build_canonical_memory_authority(
    database: Any,
    engine_client: EngineClient | None,
) -> tuple[
    MongoMemoryRepository,
    AsyncGovernedMemoryWriter | None,
]:
    repository = MongoMemoryRepository(database)
    writer = (
        None
        if engine_client is None
        else AsyncGovernedMemoryWriter(
            repository,
            storage_admitter=engine_client.admit_storage_write,
            governance_reconciler=engine_client.reconcile_governed_write,
        )
    )
    return repository, writer


_engine_client = EngineClient.from_env()
canonical_memory_repository, canonical_memory_writer = (
    build_canonical_memory_authority(
        core_db,
        _engine_client,
    )
)


async def ensure_canonical_memory_indexes() -> None:
    """Create canonical Mongo memory/revision/outbox indexes idempotently."""

    await canonical_memory_repository.ensure_indexes()


async def commit_canonical_memory(
    proposal: MemoryWriteProposal,
    *,
    review_approved: bool = False,
    now: datetime | None = None,
) -> MemoryRecord:
    """Stage and commit one policy-governed canonical memory write.

    Production writes fail closed when the engine boundary is unconfigured;
    there is intentionally no direct Mongo fallback.
    """

    if not isinstance(proposal, MemoryWriteProposal):
        raise TypeError("proposal must be MemoryWriteProposal")
    writer = canonical_memory_writer
    if writer is None:
        raise CanonicalMemoryUnavailable(
            "canonical memory engine boundary is unavailable"
        )
    writer.stage(proposal)
    return await writer.commit(
        proposal.proposal_id,
        review_approved=review_approved,
        now=now,
    )


__all__ = [
    "CanonicalMemoryUnavailable",
    "build_canonical_memory_authority",
    "canonical_memory_repository",
    "canonical_memory_writer",
    "commit_canonical_memory",
    "ensure_canonical_memory_indexes",
]
