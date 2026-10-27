"""Async Mongo-shape conversation archive: staging, failure fences and replay."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from skeleton.context.sealed_conversation_async import (
    stage_canonical_conversation_async,
    verify_staged_conversation_async,
)
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextSandwichCodec, SealedContextReplayError,
    SealedContextBoundaryError,
)


class _MongoReader:
    def __init__(self, binding, *, count=1105):
        self.thread = SimpleNamespace(
            thread_id=binding.conversation_id, version=1, message_sequence=count,
            as_dict=lambda: {"thread_id": binding.conversation_id, "version": 1, "message_sequence": count},
        )
        self.messages = tuple(
            SimpleNamespace(
                thread_id=binding.conversation_id, sequence=i, message_id=f"message-{i}",
                author_type=SimpleNamespace(value="user" if i % 2 else "assistant"),
                as_dict=lambda i=i: {"sequence": i, "content": f"unicode 🔐 {i}"},
            )
            for i in range(1, count + 1)
        )
        self.drift_at = None
        self.page_calls = 0

    async def get_thread(self, thread_id, *, tenant_id, owner_id):
        return self.thread

    async def list_messages(self, thread_id, *, tenant_id, owner_id, after_sequence=0, limit=500):
        self.page_calls += 1
        if self.drift_at == self.page_calls:
            self.thread = SimpleNamespace(
                thread_id=thread_id, version=2, message_sequence=len(self.messages),
                as_dict=lambda: {"thread_id": thread_id, "version": 2,
                                 "message_sequence": len(self.messages)},
            )
        return tuple(msg for msg in self.messages if msg.sequence > after_sequence)[:limit]


class _Sink:
    def __init__(self):
        self.frames = []
        self.completed = None
        self.aborted = False
        self.fail_on_append = False

    async def begin(self, *, binding, thread_version):
        self.binding = binding
        self.version = thread_version

    async def append(self, wire):
        if self.fail_on_append:
            raise OSError("simulated sink outage")
        self.frames.append(wire)

    async def complete(self, receipt):
        self.completed = receipt

    async def abort(self):
        self.aborted = True
        self.frames.clear()
        self.completed = None


async def _frames(frames):
    for frame in frames:
        yield frame


@pytest.fixture
def state():
    binding = ContextBinding("tenant", "owner", str(uuid4()), "model", "policy")
    codec = ContextSandwichCodec({"k1": b"z" * 32}, active_key_id="k1")
    return binding, codec


def test_async_mongo_paged_export_and_exact_recovery(state):
    binding, codec = state
    reader = _MongoReader(binding)
    sink = _Sink()

    async def work():
        receipt = await stage_canonical_conversation_async(reader, codec, sink, binding=binding)
        assert len(sink.frames) == 1106
        assert reader.page_calls == 3
        assert receipt == sink.completed and receipt.message_count == 1105
        await verify_staged_conversation_async(
            reader, codec, _frames(sink.frames), receipt, binding=binding
        )

    asyncio.run(work())


def test_staging_aborts_on_snapshot_drift(state):
    binding, codec = state
    reader, sink = _MongoReader(binding), _Sink()
    reader.drift_at = 2
    with pytest.raises(SealedContextReplayError):
        asyncio.run(stage_canonical_conversation_async(reader, codec, sink, binding=binding))
    assert sink.aborted and not sink.frames and sink.completed is None


def test_staging_aborts_on_sink_failure(state):
    binding, codec = state
    reader, sink = _MongoReader(binding, count=2), _Sink()
    sink.fail_on_append = True
    with pytest.raises(OSError):
        asyncio.run(stage_canonical_conversation_async(reader, codec, sink, binding=binding))
    assert sink.aborted


def test_missing_extra_and_wrong_tenant_fail_closed(state):
    binding, codec = state
    reader, sink = _MongoReader(binding, count=2), _Sink()

    async def work():
        receipt = await stage_canonical_conversation_async(reader, codec, sink, binding=binding)
        for frames in (sink.frames[:-1], sink.frames + [sink.frames[0]]):
            with pytest.raises(SealedContextReplayError):
                await verify_staged_conversation_async(
                    reader, codec, _frames(frames), receipt, binding=binding
                )
        with pytest.raises(SealedContextBoundaryError):
            await verify_staged_conversation_async(
                reader, codec, _frames(sink.frames), receipt,
                binding=replace(binding, tenant_id="tenant-other"),
            )
    asyncio.run(work())


def test_valid_but_stale_archive_rejected(state):
    binding, codec = state
    reader, sink = _MongoReader(binding, count=2), _Sink()

    async def work():
        receipt = await stage_canonical_conversation_async(reader, codec, sink, binding=binding)
        reader.thread = SimpleNamespace(
            thread_id=binding.conversation_id, version=2, message_sequence=2,
            as_dict=lambda: {
                "thread_id": binding.conversation_id, "version": 2, "message_sequence": 2
            },
        )
        with pytest.raises(SealedContextReplayError):
            await verify_staged_conversation_async(
                reader, codec, _frames(sink.frames), receipt, binding=binding
            )
    asyncio.run(work())


def test_empty_thread_produces_only_checkpoint(state):
    binding, codec = state
    reader, sink = _MongoReader(binding, count=0), _Sink()

    async def work():
        receipt = await stage_canonical_conversation_async(reader, codec, sink, binding=binding)
        assert receipt.message_count == 0 and len(sink.frames) == 1
        await verify_staged_conversation_async(
            reader, codec, _frames(sink.frames), receipt, binding=binding
        )
    asyncio.run(work())


def test_begin_failure_aborts_partial_staging(state):
    binding, codec = state
    reader = _MongoReader(binding, count=1)

    class BrokenBegin(_Sink):
        async def begin(self, *, binding, thread_version):
            self.frames.append(b"partial-private-object")
            raise OSError("failure mid-begin")

    sink = BrokenBegin()
    with pytest.raises(OSError):
        asyncio.run(stage_canonical_conversation_async(reader, codec, sink, binding=binding))
    assert sink.aborted and not sink.frames


def test_completion_failure_aborts_staging(state):
    binding, codec = state
    reader = _MongoReader(binding, count=1)

    class BrokenComplete(_Sink):
        async def complete(self, receipt):
            self.completed = receipt
            raise OSError("cannot stage receipt")

    sink = BrokenComplete()
    with pytest.raises(OSError):
        asyncio.run(stage_canonical_conversation_async(reader, codec, sink, binding=binding))
    assert sink.aborted and sink.completed is None and not sink.frames
