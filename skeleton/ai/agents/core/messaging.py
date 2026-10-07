"""Agent messaging — FIFO mailboxes with broadcast fall-through.

Agents on the mesh exchange envelopes; consumers pull from their own
mailbox. A message without a recipient is broadcast to every registered
mailbox. Complements negotiation with actual message transport.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional, Tuple

from skeleton.kernel.errors import AgentError


class MessagingError(AgentError):
    code = "AGT.MESSAGING"


@dataclass(frozen=True)
class Envelope:
    seq: int
    sender: str
    recipient: Optional[str]  # None means broadcast
    payload: Any


class Mailbox:
    """Per-agent deque of envelopes; the mesh writes, the agent reads."""

    def __init__(self, max_depth: int = 10_000) -> None:
        self._boxes: Dict[str, Deque[Envelope]] = {}
        self._max_depth = max_depth
        self._seq = 0
        self._total_sent = 0

    def register(self, agent: str) -> None:
        self._boxes.setdefault(agent, deque())

    def send(self, sender: str, payload: Any, recipient: Optional[str] = None) -> Envelope:
        self._seq += 1
        envelope = Envelope(seq=self._seq, sender=sender, recipient=recipient, payload=payload)
        if recipient is None:
            targets = list(self._boxes)
        else:
            targets = [recipient]
        for target in targets:
            box = self._boxes.get(target)
            if box is None:
                raise MessagingError("unknown recipient", context={"agent": target})
            if len(box) >= self._max_depth:
                raise MessagingError("mailbox full", context={"agent": target})
            box.append(envelope)
        self._total_sent += 1
        return envelope

    def poll(self, agent: str) -> Optional[Envelope]:
        box = self._boxes.get(agent)
        if box is None:
            raise MessagingError("unknown agent", context={"agent": agent})
        return box.popleft() if box else None

    def depth(self, agent: str) -> int:
        box = self._boxes.get(agent)
        return len(box) if box is not None else 0

    def stats(self) -> Dict[str, int]:
        return {
            "agents": len(self._boxes),
            "total_sent": self._total_sent,
            "pending": sum(len(b) for b in self._boxes.values()),
        }
