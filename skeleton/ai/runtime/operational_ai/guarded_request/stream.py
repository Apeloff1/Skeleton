"""Streaming response fences; never emit a partially accepted over-limit chunk."""
from __future__ import annotations

import codecs
from threading import Lock
from .contracts import strict_integer
from .errors import deny


class StreamFence:
    def __init__(self, *, max_bytes: int, max_chunks: int = 1024):
        self.max_bytes = strict_integer(max_bytes, minimum=1, maximum=1048576, field="stream-budget")
        self.max_chunks = strict_integer(max_chunks, minimum=1, maximum=65536, field="chunk-budget")
        self._lock = Lock()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        self._buffer: list[bytes] = []
        self._length = 0
        self._closed = False

    @property
    def consumed_bytes(self) -> int:
        with self._lock:
            return self._length

    def push(self, chunk: bytes) -> str:
        with self._lock:
            if self._closed:
                deny("stream-closed")
            if type(chunk) is not bytes or not chunk:
                deny("stream-chunk")
            if len(self._buffer) >= self.max_chunks or self._length + len(chunk) > self.max_bytes:
                deny("stream-exhausted")
            try:
                result = self._decoder.decode(chunk, final=False)
            except UnicodeError:
                deny("stream-utf8")
            self._buffer.append(chunk)
            self._length += len(chunk)
            return result

    def finish(self) -> str:
        with self._lock:
            if self._closed:
                deny("stream-closed")
            try:
                self._decoder.decode(b"", final=True)
            except UnicodeError:
                deny("stream-utf8")
            self._closed = True
            return b"".join(self._buffer).decode("utf-8")
