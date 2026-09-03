"""Storm gate — drop identical stimuli inside a short window. F-9."""
from __future__ import annotations

import hashlib
from typing import Any, Dict

from skeleton.kernel.dedup import DedupLedger


class Storm:
    def __init__(self, *, ttl_s: float = 8.0, capacity: int = 256) -> None:
        self.ledger = DedupLedger(ttl_s=ttl_s, capacity=capacity)
        self.seen_n = 0
        self.drop_n = 0

    def key(self, text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]

    def admit(self, text: str) -> bool:
        kid = self.key(text)
        if self.ledger.seen(kid):
            self.drop_n += 1
            return False
        self.ledger.record(kid)
        self.seen_n += 1
        return True

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-storm",
            "seen": self.seen_n,
            "drop": self.drop_n,
            "stored_prose": 0,
        }
