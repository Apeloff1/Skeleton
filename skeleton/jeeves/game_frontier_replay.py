"""Durable replay receipts for frontier admissions.

Records an ordered chain of admission digests so a session can be
replayed without re-executing the candidate stages. Candidate-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Sequence


class ReplayError(ValueError):
    pass


@dataclass
class ReplayLog:
    """Append-only log of frontier admission digests."""

    session_id: str
    entries: list[str] = field(default_factory=list)
    head: str = ""

    def append(self, admission_digest: str) -> str:
        if len(admission_digest) != 64 or any(c not in "0123456789abcdef" for c in admission_digest):
            raise ReplayError("admission_digest must be lowercase SHA-256")
        payload = json.dumps(
            {"prev": self.head, "admission": admission_digest, "index": len(self.entries)},
            sort_keys=True,
            separators=(",", ":"),
        )
        self.head = sha256(payload.encode()).hexdigest()
        self.entries.append(admission_digest)
        return self.head

    def verify(self) -> bool:
        """Recompute the chain and confirm the head."""
        head = ""
        for index, admission in enumerate(self.entries):
            payload = json.dumps(
                {"prev": head, "admission": admission, "index": index},
                sort_keys=True,
                separators=(",", ":"),
            )
            head = sha256(payload.encode()).hexdigest()
        return head == self.head and bool(self.entries)


def replay_from(session_id: str, digests: Sequence[str]) -> ReplayLog:
    log = ReplayLog(session_id=session_id)
    for digest in digests:
        log.append(digest)
    return log
