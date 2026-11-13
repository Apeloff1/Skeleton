"""B061 - pluggable transports behind the ``Transport`` contract.

A transport moves opaque datagrams; framing lives in :mod:`.contracts`.
"""
from __future__ import annotations

import json
import socket
from collections import deque
from typing import Iterator, Optional, Protocol

from .contracts import BinaryFrameCodec, FrameError, Message, MessageKind, StreamDecoder


class Transport(Protocol):
    def send(self, data: bytes) -> None: ...

    def recv(self) -> Optional[bytes]: ...

    def close(self) -> None: ...


class InMemoryTransport:
    """Deterministic in-process datagram pipe. ``pair()`` returns two linked ends."""

    def __init__(self) -> None:
        self.inbox: deque[bytes] = deque()
        self.peer: Optional["InMemoryTransport"] = None
        self.closed = False

    @classmethod
    def pair(cls) -> tuple["InMemoryTransport", "InMemoryTransport"]:
        a, b = cls(), cls()
        a.peer, b.peer = b, a
        return a, b

    def send(self, data: bytes) -> None:
        if self.closed or self.peer is None or self.peer.closed:
            raise ConnectionError("transport closed")
        self.peer.inbox.append(bytes(data))

    def recv(self) -> Optional[bytes]:
        return self.inbox.popleft() if self.inbox else None

    def close(self) -> None:
        self.closed = True


class UdpLoopbackTransport:
    """Non-blocking UDP socket bound to 127.0.0.1 only."""

    def __init__(self, port: int = 0, max_datagram: int = 1500) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port))
        self.sock.setblocking(False)
        self.address = self.sock.getsockname()
        self.remote: Optional[tuple] = None
        self.max_datagram = max_datagram

    def connect(self, address: tuple) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("loopback only")
        self.remote = address

    def send(self, data: bytes) -> None:
        if self.remote is None:
            raise ConnectionError("no remote")
        self.sock.sendto(data, self.remote)

    def recv(self) -> Optional[bytes]:
        try:
            data, addr = self.sock.recvfrom(self.max_datagram)
        except (BlockingIOError, InterruptedError):
            return None
        if self.remote is not None and addr != self.remote:
            return None  # ignore spoofed / foreign senders
        return data

    def close(self) -> None:
        self.sock.close()


class TcpLoopbackTransport:
    """Stream transport over a connected loopback socket, re-framed to datagrams."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.sock.setblocking(False)
        self._decoder = StreamDecoder()
        self._codec = BinaryFrameCodec()
        self._ready: deque[bytes] = deque()

    @classmethod
    def pair(cls) -> tuple["TcpLoopbackTransport", "TcpLoopbackTransport"]:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        c = socket.create_connection(srv.getsockname(), timeout=2)
        s, _ = srv.accept()
        srv.close()
        return cls(c), cls(s)

    def send(self, data: bytes) -> None:
        self.sock.setblocking(True)
        try:
            self.sock.sendall(data)
        finally:
            self.sock.setblocking(False)

    def recv(self) -> Optional[bytes]:
        if not self._ready:
            try:
                chunk = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                chunk = None
            if chunk:
                for msg in self._decoder.feed(chunk):
                    self._ready.append(self._codec.encode(msg))
        return self._ready.popleft() if self._ready else None

    def close(self) -> None:
        self.sock.close()


class SSEMessageAdapter:
    """Receive-only adapter over the realtime SSE parser (skeleton.realtime.sse).

    Reuses the canonical parser rather than a second implementation; each SSE
    ``data`` JSON object ``{"kind": int, "channel": int, "seq": int, "payload": str}``
    becomes a contract :class:`Message`. Non-conforming events are dropped.
    """

    def __init__(self) -> None:
        from skeleton.realtime.sse import SSEParser  # lazy: keeps netcode import-light

        self._parser = SSEParser()
        self.dropped = 0

    def feed(self, chunk: str) -> Iterator[Message]:
        for sse in self._parser.feed(chunk):
            try:
                obj = json.loads(sse.data)
                if not isinstance(obj, dict):
                    raise ValueError
                yield Message(MessageKind(int(obj["kind"])), str(obj.get("payload", "")).encode("utf-8"),
                              int(obj.get("channel", 0)), int(obj.get("seq", 0)))
            except (ValueError, KeyError, TypeError, FrameError):
                self.dropped += 1
