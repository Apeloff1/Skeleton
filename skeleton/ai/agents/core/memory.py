"""Agent working memory — bounded short-term buffer.

Deliberation needs scratch space; the mesh shouldn't carry its whole
context. WorkingMemory queues (kind, payload) with a rough token budget
and evicts the oldest when it overflows.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterator, Tuple

from skeleton.kernel.errors import AgentError


class MemoryError(AgentError):
    code = "AGT.MEMORY"


@dataclass(frozen=True)
class MemoryEntry:
    kind: str
    payload: object
    tokens: int


class WorkingMemory:
    """FIFO buffer with token-budget eviction."""

    def __init__(self, *, max_tokens: int = 4096) -> None:
        if max_tokens <= 0:
            raise MemoryError("max_tokens must be positive")
        self._max_tokens = max_tokens
        self._buffer: Deque[MemoryEntry] = deque()
        self._total = 0

    def append(self, kind: str, payload: object) -> MemoryEntry:
        tokens = max(1, len(str(payload)) // 4)
        entry = MemoryEntry(kind=kind, payload=payload, tokens=tokens)
        self._buffer.append(entry)
        self._total += tokens
        while self._total > self._max_tokens and self._buffer:
            evicted = self._buffer.popleft()
            self._total -= evicted.tokens
        return entry

    def snapshot(self) -> Tuple[MemoryEntry, ...]:
        return tuple(self._buffer)

    def token_count(self) -> int:
        return self._total

    def capacity(self) -> int:
        return self._max_tokens

    def flush(self) -> None:
        self._buffer.clear()
        self._total = 0
