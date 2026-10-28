"""Streaming blob sealing and byte-exact recovery across adversarial boundaries."""

from __future__ import annotations

from dataclasses import replace
import io
from uuid import uuid4

import pytest

from skeleton.context.sealed_blobs import (
    restore_blob_bytes, restore_blob_to_staging, seal_blob_frames,
)
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextHead, ContextSandwichCodec, SealedContextBoundaryError,
    SealedContextError, SealedContextIntegrityError, SealedContextLimitError,
    SealedContextReplayError,
)


@pytest.fixture
def state():
    return (
        ContextBinding("tenant", "user", str(uuid4()), "model", "policy"),
        ContextSandwichCodec({"v1": b"k" * 32}, active_key_id="v1"),
    )


def _seal(data, state, *, object_id="asset-1", chunk_bytes=1024):
    binding, codec = state
    pairs = list(seal_blob_frames(
        io.BytesIO(data), codec, binding=binding, object_id=object_id,
        chunk_bytes=chunk_bytes,
    ))
    return [wire for wire, _ in pairs], pairs[-1][1]


def test_streams_original_bytes_without_normalizing_unicode_or_binary(state):
    data = (b"\x00\xff" + "🐉\r\n".encode()) * 17001
    wires, head = _seal(data, state)
    sink = io.BytesIO()
    assert restore_blob_to_staging(
        wires, sink, state[1], binding=state[0], object_id="asset-1", trusted_head=head,
    ) == len(data)
    assert sink.getvalue() == data


def test_zero_length_object_has_authenticated_terminal(state):
    wires, head = _seal(b"", state)
    assert len(wires) == 1
    assert restore_blob_bytes(
        wires, state[1], binding=state[0], object_id="asset-1", trusted_head=head
    ) == b""


def test_reject_missing_reordered_duplicate_tail_and_wrong_object(state):
    wires, head = _seal(b"secret" * 500, state)
    for invalid in (wires[:-1], wires[1:], wires[:1] + wires[:1] + wires[1:], wires[::-1]):
        with pytest.raises((SealedContextReplayError, SealedContextIntegrityError)):
            restore_blob_to_staging(
                invalid, io.BytesIO(), state[1], binding=state[0],
                object_id="asset-1", trusted_head=head,
            )
    with pytest.raises(SealedContextReplayError):
        restore_blob_to_staging(
            wires, io.BytesIO(), state[1], binding=state[0],
            object_id="asset-2", trusted_head=head,
        )
    with pytest.raises(SealedContextBoundaryError):
        restore_blob_to_staging(
            wires, io.BytesIO(), state[1], binding=replace(state[0], tenant_id="other"),
            object_id="asset-1", trusted_head=head,
        )


def test_reject_stale_head_and_budget_overrun(state):
    wires, head = _seal(b"more than ten", state)
    with pytest.raises(SealedContextReplayError):
        restore_blob_to_staging(
            wires, io.BytesIO(), state[1], binding=state[0],
            object_id="asset-1", trusted_head=ContextHead(),
        )
    with pytest.raises(SealedContextLimitError):
        restore_blob_to_staging(
            wires, io.BytesIO(), state[1], binding=state[0],
            object_id="asset-1", trusted_head=head, max_object_bytes=10,
        )
    with pytest.raises(SealedContextLimitError):
        list(seal_blob_frames(
            io.BytesIO(b"12"), state[1], binding=state[0],
            object_id="asset-1", max_object_bytes=1,
        ))
    with pytest.raises(SealedContextError):
        list(seal_blob_frames(
            io.BytesIO(b"x"), state[1], binding=state[0], object_id="../../bad",
        ))


def test_small_object_convenience_and_nonseekable_short_write(state):
    wires, head = _seal(b"contents", state)
    assert restore_blob_bytes(
        wires, state[1], binding=state[0], object_id="asset-1", trusted_head=head
    ) == b"contents"

    class ShortWriter:
        def write(self, data):
            return len(data) - 1

    with pytest.raises(SealedContextError):
        restore_blob_to_staging(
            wires, ShortWriter(), state[1], binding=state[0], object_id="asset-1",
            trusted_head=head,
        )
