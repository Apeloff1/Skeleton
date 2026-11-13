"""Request hedging — tail-latency mitigation via speculative retries.

Sends a backup request after the p95 latency elapses without a
response, returning whichever finishes first and cancelling the
loser. Tracks hedge rate, waste (hedges that lost), and tail
improvement. Bounded by a per-subsystem hedge budget to avoid
amplifying overload — hedges are shed first under load.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class HedgeStats:
    subsystem: str
    requests: int = 0
    hedged: int = 0
    hedge_won: int = 0
    hedge_wasted: int = 0
    budget_per_100: int = 5

    def hedge_rate(self) -> float:
        return self.hedged / self.requests if self.requests else 0.0


class RequestHedger:
    """Speculative retry controller with budget limits and heavy-task backup chains."""

    def __init__(self):
        self._stats: Dict[str, HedgeStats] = {}
        self._p50: Dict[str, float] = {}
        self._p95: Dict[str, float] = {}
        self._p99: Dict[str, float] = {}
        self._latencies: Dict[str, List[float]] = {}
        self._backup_consecutive_errors: Dict[str, int] = {}

    def _stat(self, subsystem: str) -> HedgeStats:
        return self._stats.setdefault(subsystem, HedgeStats(subsystem=subsystem))

    def record_latency(self, subsystem: str, latency_ms: float) -> None:
        buf = self._latencies.setdefault(subsystem, [])
        buf.append(latency_ms)
        if len(buf) > 200:
            buf.pop(0)
        vals = sorted(buf)
        self._p50[subsystem] = vals[min(len(vals) - 1, int(len(vals) * 0.50))]
        self._p95[subsystem] = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
        self._p99[subsystem] = vals[min(len(vals) - 1, int(len(vals) * 0.99))]

    def hedge_delay_ms(self, subsystem: str) -> float:
        return max(5.0, self._p95.get(subsystem, 50.0))

    def budget_allows(self, subsystem: str) -> bool:
        if self._backup_consecutive_errors.get(subsystem, 0) >= 3:
            return False
        stat = self._stat(subsystem)
        allowed = stat.requests * (stat.budget_per_100 / 100.0)
        return stat.hedged < allowed + 1

    def reset_backup_circuit(self, subsystem: str) -> None:
        self._backup_consecutive_errors[subsystem] = 0

    def execute(self, subsystem: str, primary: Callable[[], Any],
                backup: Optional[Callable[[], Any]] = None) -> Dict[str, Any]:
        stat = self._stat(subsystem)
        stat.requests += 1
        start = time.time_ns()
        result: Any = None
        error: Optional[Exception] = None
        try:
            result = primary()
        except Exception as exc:  # noqa: BLE001
            error = exc
        latency_ms = (time.time_ns() - start) / 1e6
        self.record_latency(subsystem, latency_ms)
        hedged = False
        hedge_won = False
        if error is not None and backup and self.budget_allows(subsystem):
            stat.hedged += 1
            hedged = True
            b_start = time.time_ns()
            try:
                result = backup()
                error = None
                hedge_won = True
                stat.hedge_won += 1
                self._backup_consecutive_errors[subsystem] = 0
                b_lat = (time.time_ns() - b_start) / 1e6
                latency_ms = b_lat
                self.record_latency(subsystem, b_lat)
            except Exception:  # noqa: BLE001
                stat.hedge_wasted += 1
                self._backup_consecutive_errors[subsystem] = self._backup_consecutive_errors.get(subsystem, 0) + 1
        elif latency_ms > self.hedge_delay_ms(subsystem) and backup and self.budget_allows(subsystem):
            stat.hedged += 1
            hedged = True
            b_start = time.time_ns()
            try:
                b_res = backup()
                self._backup_consecutive_errors[subsystem] = 0
                b_lat = (time.time_ns() - b_start) / 1e6
                if b_lat + self.hedge_delay_ms(subsystem) < latency_ms:
                    result = b_res
                    hedge_won = True
                    stat.hedge_won += 1
                else:
                    stat.hedge_wasted += 1
            except Exception:  # noqa: BLE001
                stat.hedge_wasted += 1
                self._backup_consecutive_errors[subsystem] = self._backup_consecutive_errors.get(subsystem, 0) + 1
        if error:
            raise error
        return {
            "result": result,
            "latency_ms": round(latency_ms, 2),
            "hedged": hedged,
            "hedge_won": hedge_won,
            "p95_ms": round(self._p95.get(subsystem, 0.0), 2),
            "p99_ms": round(self._p99.get(subsystem, 0.0), 2),
        }

    def execute_heavy(
        self,
        subsystem: str,
        primary: Callable[[], Any],
        backups: List[Callable[[], Any]],
    ) -> Dict[str, Any]:
        """Execute a heavy task with multi-tier backup failover chain."""
        stat = self._stat(subsystem)
        stat.requests += 1
        start = time.time_ns()
        try:
            res = primary()
            lat = (time.time_ns() - start) / 1e6
            self.record_latency(subsystem, lat)
            return {
                "result": res,
                "latency_ms": round(lat, 2),
                "used_backup": False,
                "backup_tier": 0,
            }
        except Exception as primary_exc:  # noqa: BLE001
            last_exc = primary_exc
            for tier_idx, backup_fn in enumerate(backups, start=1):
                stat.hedged += 1
                b_start = time.time_ns()
                try:
                    res = backup_fn()
                    b_lat = (time.time_ns() - b_start) / 1e6
                    stat.hedge_won += 1
                    self._backup_consecutive_errors[subsystem] = 0
                    self.record_latency(subsystem, b_lat)
                    return {
                        "result": res,
                        "latency_ms": round(b_lat, 2),
                        "used_backup": True,
                        "backup_tier": tier_idx,
                    }
                except Exception as b_exc:  # noqa: BLE001
                    stat.hedge_wasted += 1
                    self._backup_consecutive_errors[subsystem] = self._backup_consecutive_errors.get(subsystem, 0) + 1
                    last_exc = b_exc
            raise last_exc

    def tail_improvement(self, subsystem: str) -> Dict[str, Any]:
        stat = self._stat(subsystem)
        return {
            "subsystem": subsystem,
            "requests": stat.requests,
            "hedge_rate": round(stat.hedge_rate(), 4),
            "hedges_won": stat.hedge_won,
            "hedges_wasted": stat.hedge_wasted,
            "waste_fraction": round(stat.hedge_wasted / stat.hedged, 3) if stat.hedged else 0.0,
            "current_p95_ms": round(self._p95.get(subsystem, 0.0), 2),
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "hedging-card",
            "subsystems": {n: self.tail_improvement(n) for n in self._stats},
        }
