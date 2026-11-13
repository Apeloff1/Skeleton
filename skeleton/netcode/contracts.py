"""B061 - stable session/message contracts and a fuzzable binary frame codec.

Wire frame (big-endian, 20-byte header + payload)::

    magic   2s  b"SK"
    version H   protocol version of the sender
    kind    B   MessageKind
    flags   B   reserved, must be 0
    channel H   logical channel
    seq     I   sender sequence number (wraps at 2**32)
    ack     I   highest remote seq received
    length  H   payload length (<= MAX_PAYLOAD)
    payload length bytes
    crc32   I   over header+payload

Parsers never raise anything but :class:`FrameError` on hostile input.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterator, Optional, Protocol

PROTOCOL_VERSION = 3
MIN_COMPATIBLE_VERSION = 2
MAGIC = b"SK"
MAX_PAYLOAD = 1200  # stays under a typical 1280-byte IPv6 MTU with headers
_HEADER = struct.Struct(">2sHBBHIIH")
_CRC = struct.Struct(">I")
HEADER_SIZE = _HEADER.size
FRAME_OVERHEAD = HEADER_SIZE + _CRC.size


class FrameError(ValueError):
    """Raised for any malformed, oversized, or corrupted frame."""


class MessageKind(IntEnum):
    HELLO = 1
    WELCOME = 2
    REJECT = 3
    INPUT = 4
    SNAPSHOT = 5
    ACK = 6
    PING = 7
    PONG = 8
    DISCONNECT = 9
    RELIABLE = 10


@dataclass(frozen=True, slots=True)
class Message:
    kind: MessageKind
    payload: bytes = b""
    channel: int = 0
    seq: int = 0
    ack: int = 0
    version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.payload, (bytes, bytearray)):
            raise FrameError("payload must be bytes")
        if len(self.payload) > MAX_PAYLOAD:
            raise FrameError("payload too large")
        for name, hi in (("channel", 0xFFFF), ("seq", 0xFFFFFFFF), ("ack", 0xFFFFFFFF), ("version", 0xFFFF)):
            v = getattr(self, name)
            if not isinstance(v, int) or not 0 <= v <= hi:
                raise FrameError(f"{name} out of range")


class Codec(Protocol):
    """Stable codec contract: transports carry bytes, sessions carry Messages."""

    def encode(self, message: Message) -> bytes: ...

    def decode(self, data: bytes) -> Message: ...


class BinaryFrameCodec:
    """Default versioned codec. ``decode`` is total: bytes in, Message or FrameError."""

    def encode(self, message: Message) -> bytes:
        head = _HEADER.pack(MAGIC, message.version, int(message.kind), 0, message.channel,
                            message.seq, message.ack, len(message.payload))
        body = head + bytes(message.payload)
        return body + _CRC.pack(zlib.crc32(body) & 0xFFFFFFFF)

    def decode(self, data: bytes) -> Message:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise FrameError("frame must be bytes")
        data = bytes(data)
        if len(data) < FRAME_OVERHEAD:
            raise FrameError("short frame")
        magic, version, kind, flags, channel, seq, ack, length = _HEADER.unpack_from(data)
        if magic != MAGIC:
            raise FrameError("bad magic")
        if flags != 0:
            raise FrameError("reserved flags set")
        if length > MAX_PAYLOAD:
            raise FrameError("payload too large")
        if len(data) != FRAME_OVERHEAD + length:
            raise FrameError("length mismatch")
        body = data[: HEADER_SIZE + length]
        (crc,) = _CRC.unpack_from(data, HEADER_SIZE + length)
        if crc != zlib.crc32(body) & 0xFFFFFFFF:
            raise FrameError("checksum mismatch")
        try:
            mk = MessageKind(kind)
        except ValueError:
            raise FrameError("unknown message kind") from None
        return Message(mk, body[HEADER_SIZE:], channel, seq, ack, version)


class StreamDecoder:
    """Incremental decoder for stream transports (TCP): frames may split anywhere.

    On corruption it raises FrameError and poisons itself; stream framing cannot
    resynchronise safely, so the session must be dropped.
    """

    def __init__(self, codec: Optional[BinaryFrameCodec] = None, max_buffer: int = 64 * 1024) -> None:
        self._codec = codec or BinaryFrameCodec()
        self._buf = bytearray()
        self._max = max_buffer
        self._dead = False

    def feed(self, chunk: bytes) -> Iterator[Message]:
        if self._dead:
            raise FrameError("decoder poisoned")
        self._buf += chunk
        if len(self._buf) > self._max:
            self._dead = True
            raise FrameError("stream buffer overflow")
        while len(self._buf) >= HEADER_SIZE:
            if bytes(self._buf[:2]) != MAGIC:
                self._dead = True
                raise FrameError("bad magic")
            length = struct.unpack_from(">H", self._buf, HEADER_SIZE - 2)[0]
            if length > MAX_PAYLOAD:
                self._dead = True
                raise FrameError("payload too large")
            total = FRAME_OVERHEAD + length
            if len(self._buf) < total:
                return
            frame, self._buf = bytes(self._buf[:total]), self._buf[total:]
            try:
                yield self._codec.decode(frame)
            except FrameError:
                self._dead = True
                raise


def is_compatible(version: int) -> bool:
    return MIN_COMPATIBLE_VERSION <= version <= PROTOCOL_VERSION


def _seq_newer(a: int, b: int) -> bool:
    """True if sequence ``a`` is newer than ``b`` with 32-bit wraparound."""
    return a != b and ((a - b) & 0xFFFFFFFF) < 0x80000000


class Session:
    """Transport-agnostic session contract: sequencing, acks, version, liveness.

    Works with any object exposing ``send(bytes)`` / ``recv() -> bytes | None``.
    Malformed or stale datagrams are counted and dropped, never raised.
    """

    def __init__(self, transport, codec: Optional[Codec] = None, *, version: int = PROTOCOL_VERSION) -> None:
        self.transport = transport
        self.codec = codec or BinaryFrameCodec()
        self.version = version
        self.local_seq = 0
        self.remote_seq: Optional[int] = None
        self.remote_version: Optional[int] = None
        self.stats = {"sent": 0, "received": 0, "malformed": 0, "stale": 0, "duplicate": 0}
        self._seen: set[int] = set()

    def send(self, kind: MessageKind, payload: bytes = b"", channel: int = 0) -> Message:
        self.local_seq = (self.local_seq + 1) & 0xFFFFFFFF
        msg = Message(kind, payload, channel, self.local_seq, self.remote_seq or 0, self.version)
        self.transport.send(self.codec.encode(msg))
        self.stats["sent"] += 1
        return msg

    def poll(self) -> list[Message]:
        out: list[Message] = []
        while (raw := self.transport.recv()) is not None:
            try:
                msg = self.codec.decode(raw)
            except FrameError:
                self.stats["malformed"] += 1
                continue
            if msg.seq in self._seen:
                self.stats["duplicate"] += 1
                continue
            self._seen.add(msg.seq)
            if len(self._seen) > 1024:
                self._seen = {s for s in self._seen if not _seq_newer(msg.seq, (s + 512) & 0xFFFFFFFF)}
            if self.remote_seq is None or _seq_newer(msg.seq, self.remote_seq):
                self.remote_seq = msg.seq
            elif msg.kind in (MessageKind.SNAPSHOT, MessageKind.INPUT):
                # unreliable state superseded by a newer one already delivered
                self.stats["stale"] += 1
                continue
            self.remote_version = msg.version
            self.stats["received"] += 1
            out.append(msg)
        return out
