"""Lossless streaming binary-object staging over authenticated context frames.

Encrypted blob frames are optional recovery aids. Neither bytes nor metadata
become authoritative until the existing owning store commits them transactionally.
Write recovered bytes only to a disposable staging destination until the final
trusted-head comparison and decrypted terminal digest have both succeeded.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import BinaryIO, Iterable, Iterator

from skeleton.context.sealed_events import ContextEvent, decode_event, encode_event
from skeleton.context.sealed_sandwich import (
    ContextBinding,
    ContextHead,
    ContextSandwichCodec,
    SealedContextError,
    SealedContextIntegrityError,
    SealedContextLimitError,
    SealedContextReplayError,
)


CHUNK_BYTES = 256 * 1024
MAX_OBJECT_BYTES = 8 * 1024 * 1024 * 1024
MAX_OBJECT_CHUNKS = 1_000_000 - 1  # reserve last frame for receipt
_FORMAT = 1


def _object_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in value)
    ):
        raise SealedContextError("invalid object identity")
    return value


def _terminal_bytes(object_id: str, size: int, count: int, digest: str) -> bytes:
    return json.dumps(
        {"version": _FORMAT, "object_id": object_id, "size": size,
         "chunk_count": count, "sha256": digest},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def seal_blob_frames(
    source: BinaryIO,
    codec: ContextSandwichCodec,
    *,
    binding: ContextBinding,
    object_id: str,
    previous: ContextHead = ContextHead(),
    chunk_bytes: int = CHUNK_BYTES,
    max_object_bytes: int = MAX_OBJECT_BYTES,
) -> Iterator[tuple[bytes, ContextHead]]:
    """Stream exact source bytes with a final encrypted integrity receipt.

    Yielded heads are *candidates*; an externally stored authoritative head and
    atomically published frame sequence are mandatory before recovery use.
    Discard all staged frames if generator execution fails or is not exhausted.
    """
    object_id = _object_id(object_id)
    if type(chunk_bytes) is not int or not 1 <= chunk_bytes <= CHUNK_BYTES:
        raise SealedContextLimitError("unsupported object chunk size")
    if type(max_object_bytes) is not int or not 0 <= max_object_bytes <= MAX_OBJECT_BYTES:
        raise SealedContextLimitError("unsupported object size budget")
    hasher = hashlib.sha256()
    size, count, head = 0, 0, previous
    while True:
        chunk = source.read(chunk_bytes)
        if not isinstance(chunk, bytes) or len(chunk) > chunk_bytes:
            raise SealedContextError("binary source returned invalid or oversized bytes")
        if not chunk:
            break
        size += len(chunk)
        count += 1
        if size > max_object_bytes or count > MAX_OBJECT_CHUNKS:
            raise SealedContextLimitError("object exceeds archive budget")
        hasher.update(chunk)
        event = ContextEvent(f"blob:{object_id}:{count}", "evidence", chunk, f"blob:{object_id}")
        wire, head = codec.seal(encode_event(event), binding=binding, previous=head)
        yield wire, head
    receipt = ContextEvent(
        f"blob:{object_id}:end", "receipt",
        _terminal_bytes(object_id, size, count, hasher.hexdigest()), f"blob:{object_id}",
    )
    wire, head = codec.seal(encode_event(receipt), binding=binding, previous=head)
    yield wire, head


def restore_blob_to_staging(
    wires: Iterable[bytes],
    output: BinaryIO,
    codec: ContextSandwichCodec,
    *,
    binding: ContextBinding,
    object_id: str,
    trusted_head: ContextHead,
    starting_head: ContextHead = ContextHead(),
    max_object_bytes: int = MAX_OBJECT_BYTES,
) -> int:
    """Verify and stage binary bytes; never expose output before return success.

    A caller must discard the *entire* output staging object on any failure.
    If the starting/trusted heads came from an untrusted client, anti-replay
    protection is void. The sealed terminal digest is not a signature.
    """
    object_id = _object_id(object_id)
    if type(max_object_bytes) is not int or not 0 <= max_object_bytes <= MAX_OBJECT_BYTES:
        raise SealedContextLimitError("unsupported object size budget")
    if starting_head.sequence > trusted_head.sequence:
        raise SealedContextReplayError("starting head exceeds committed object head")
    current, count, size = starting_head, 0, 0
    hasher = hashlib.sha256()
    terminated = False
    for wire in wires:
        frame = codec.open(wire, binding=binding, previous=current)
        current = frame.head
        event = decode_event(frame.payload)
        if event.source_ref != f"blob:{object_id}" or terminated:
            raise SealedContextReplayError("object frame crossed identity or terminal boundary")
        if event.kind == "receipt" and event.event_id == f"blob:{object_id}:end":
            if event.content != _terminal_bytes(object_id, size, count, hasher.hexdigest()):
                raise SealedContextIntegrityError("object terminal digest or size mismatch")
            terminated = True
        elif event.kind == "evidence" and event.event_id == f"blob:{object_id}:{count + 1}":
            count += 1
            size += len(event.content)
            if count > MAX_OBJECT_CHUNKS or size > max_object_bytes or not event.content:
                raise SealedContextLimitError("object byte or chunk budget exceeded")
            hasher.update(event.content)
            if output.write(event.content) != len(event.content):
                raise SealedContextError("staging output accepted a partial object write")
        else:
            raise SealedContextReplayError("object frame is missing or out of order")
    if not terminated or current != trusted_head:
        raise SealedContextReplayError("object archive is not complete at its trusted head")
    return size


def restore_blob_bytes(
    wires: Iterable[bytes], codec: ContextSandwichCodec, *, binding: ContextBinding,
    object_id: str, trusted_head: ContextHead, max_object_bytes: int = CHUNK_BYTES,
) -> bytes:
    """Small-object convenience; bounded to avoid untrusted in-memory allocation."""
    if type(max_object_bytes) is not int or not 0 <= max_object_bytes <= CHUNK_BYTES:
        raise SealedContextLimitError("in-memory restore size exceeds safe limit")
    output = io.BytesIO()
    restore_blob_to_staging(
        wires, output, codec, binding=binding, object_id=object_id,
        trusted_head=trusted_head, max_object_bytes=max_object_bytes,
    )
    return output.getvalue()
