"""Counters and snapshots for OmniFabric operations."""
from __future__ import annotations

import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FabricMetrics:
    appends_ok: int = 0
    appends_failed: int = 0
    verify_ok: int = 0
    verify_failed: int = 0
    queries: int = 0
    replays: int = 0
    windows_sealed: int = 0
    checkpoints: int = 0
    subscriber_deliveries: int = 0
    bytes_payload_approx: int = 0
    kind_counts: Counter = field(default_factory=Counter)
    ledger_counts: Counter = field(default_factory=Counter)
    started_at: float = field(default_factory=time.time)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def record_append(self, *, ok: bool, ledger: str = "", kind: str = "", payload_bytes: int = 0) -> None:
        with self._lock:
            if ok:
                self.appends_ok += 1
                if ledger:
                    self.ledger_counts[ledger] += 1
                if kind:
                    self.kind_counts[kind] += 1
                self.bytes_payload_approx += max(0, payload_bytes)
            else:
                self.appends_failed += 1

    def record_verify(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self.verify_ok += 1
            else:
                self.verify_failed += 1

    def record_query(self) -> None:
        with self._lock:
            self.queries += 1

    def record_replay(self) -> None:
        with self._lock:
            self.replays += 1

    def record_window(self) -> None:
        with self._lock:
            self.windows_sealed += 1

    def record_checkpoint(self) -> None:
        with self._lock:
            self.checkpoints += 1

    def record_delivery(self, n: int = 1) -> None:
        with self._lock:
            self.subscriber_deliveries += n

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "appends_ok": self.appends_ok,
                "appends_failed": self.appends_failed,
                "verify_ok": self.verify_ok,
                "verify_failed": self.verify_failed,
                "queries": self.queries,
                "replays": self.replays,
                "windows_sealed": self.windows_sealed,
                "checkpoints": self.checkpoints,
                "subscriber_deliveries": self.subscriber_deliveries,
                "bytes_payload_approx": self.bytes_payload_approx,
                "kind_counts": dict(self.kind_counts),
                "ledger_counts": dict(self.ledger_counts),
                "uptime_s": time.time() - self.started_at,
            }
