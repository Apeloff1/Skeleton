"""Sticky protected writer bindings deny loss of source epoch before mutation."""
import asyncio
from types import SimpleNamespace
import pytest

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError, configured_canonical_epoch,
    fence_conversation_write, fence_memory_commit, fence_memory_tombstone,
    fence_memento_write,
)


def owner():
    epoch = object.__new__(MongoCanonicalSourceEpoch)
    return SimpleNamespace(canonical_source_epoch=epoch,
                           _required_canonical_source_epoch=epoch), epoch


def test_legacy_owner_remains_distinct_from_protected_owner():
    assert configured_canonical_epoch(SimpleNamespace()) is None
    actual, epoch = owner()
    assert configured_canonical_epoch(actual) is epoch
    for replacement in (None, object(), object.__new__(MongoCanonicalSourceEpoch)):
        actual.canonical_source_epoch = replacement
        with pytest.raises(MongoSourceEpochError, match="binding changed"):
            configured_canonical_epoch(actual)


def test_all_known_outer_fences_deny_missing_epoch_before_mutation():
    async def run():
        actual, _ = owner()
        actual.canonical_source_epoch = None
        async def mutate(*args, **kwargs):
            pytest.fail("mutation reached unguarded owner")
        calls = (
            fence_conversation_write(mutate)(actual, tenant_id="tenant", owner_id="actor"),
            fence_memory_commit(mutate)(actual, object()),
            fence_memory_tombstone(mutate)(actual, "memory"),
            fence_memento_write(mutate)(SimpleNamespace(conversation=actual),
                                        tenant_id="tenant", owner_id="actor", thread_id="thread"),
        )
        for call in calls:
            with pytest.raises(MongoSourceEpochError, match="binding changed"):
                await call
    asyncio.run(run())


def test_internal_memory_writer_guard_cannot_downgrade():
    from skeleton.persistence.memory_repository import MongoMemoryRepository
    actual, epoch = owner()
    memory = object.__new__(MongoMemoryRepository)
    memory.canonical_source_epoch = None
    memory._required_canonical_source_epoch = epoch
    with pytest.raises(MongoSourceEpochError, match="binding changed"):
        memory._require_canonical_writer(tenant_id="tenant", actor_id="actor")
