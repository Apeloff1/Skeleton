"""Instantiate stock modules so they are not just import probes."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.checkpoint import CheckpointStore
from skeleton.kernel.dedup import DedupLedger
from skeleton.kernel.entropy import EntropyPool
from skeleton.kernel.telemetry import SlidingCounter


class StockLive:
    def __init__(self, *, mobile: bool = True) -> None:
        self.entropy = EntropyPool(seed=7)
        self.dedup = DedupLedger(ttl_s=60.0, capacity=256 if mobile else 4096)
        self.ckpt = CheckpointStore(retain=2 if mobile else 4)
        self.counter = SlidingCounter(window_s=30.0)
        self.saves = 0

    def tick(self, key: str = "pulse") -> Dict[str, Any]:
        blob = self.entropy.random_bytes(8)
        try:
            self.ckpt.save("organism", self.saves + 1, {"key": key})
            self.saves += 1
        except Exception:
            pass
        self.counter.hit(1)
        return {
            "kind": "stock-live",
            "entropy": len(blob) if blob is not None else 0,
            "saves": self.saves,
            "stored_prose": 0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-stock-live",
            "saves": self.saves,
            "live": ("entropy", "dedup", "ckpt", "counter"),
            "stored_prose": 0,
        }
