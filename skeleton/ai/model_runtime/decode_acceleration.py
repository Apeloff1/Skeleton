"""Exact request-local decode auxiliaries; no persistent data or model authority.

The runtime still owns identity, bounds, generated tokens and receipts.
A rolling frequency table removes repeated history scans. A bounded word
decoder matcher avoids reconstructing the whole output for each stop check.
BPE, custom decoders and any non-append-only policy retain canonical decode.
"""
from __future__ import annotations

from collections import Counter, deque


class RollingPenaltyWindow:
    """Maintain exact multiplicities of the last W admitted token IDs."""

    def __init__(self, history, window: int):
        if type(window) is not int or window < 1:
            raise ValueError("positive repetition window required")
        self.window = window
        recent = history[-window:]
        self.tokens = deque(recent)
        self.counts = Counter(recent)

    def append(self, token: int) -> None:
        if len(self.tokens) == self.window:
            old = self.tokens.popleft()
            count = self.counts[old] - 1
            if count:
                self.counts[old] = count
            else:
                del self.counts[old]
        self.tokens.append(token)
        self.counts[token] += 1


class WordStopMatcher:
    """Exact earliest character match for canonical space-joined pieces.

    Retain at most max marker length minus one preceding characters, plus
    absolute offset and earliest match. Observe every generated token,
    including those before minimum output length. On eligibility, the
    actual tokenizer decodes once and verifies the observed index.
    """

    def __init__(self, markers: tuple[str, ...]):
        if (type(markers) is not tuple or not 1 <= len(markers) <= 16
                or any(type(m) is not str or not 1 <= len(m) <= 256 for m in markers)):
            raise ValueError("bounded stop markers required")
        self.markers = markers
        self.keep = max(map(len, markers)) - 1
        self.tail = ""
        self.length = 0
        self.tokens = 0
        self.first: int | None = None

    def append(self, piece: str) -> None:
        if type(piece) is not str:
            raise ValueError("word tokenizer piece must be text")
        delta = (" " if self.tokens else "") + piece
        # A previously found match might be preceded by a longer marker
        # that finishes only now. Continue scanning until the runtime
        # actually stops; never early-return merely because first exists.
        joined = self.tail + delta
        origin = self.length - len(self.tail)
        for marker in self.markers:
            offset = joined.find(marker)
            if offset >= 0:
                candidate = origin + offset
                if self.first is None or candidate < self.first:
                    self.first = candidate
        self.length += len(delta)
        self.tokens += 1
        self.tail = joined[-self.keep:] if self.keep else ""

    def verify(self, decoded: str) -> int:
        # Do not publish a stop position from an auxiliary if the canonical
        # decoder's output differs from its append-only contract.
        offsets = [decoded.find(marker) for marker in self.markers]
        found = min((i for i in offsets if i >= 0), default=None)
        if len(decoded) != self.length or found != self.first or found is None:
            raise ValueError("incremental stop detector differs from canonical decoding")
        return found
