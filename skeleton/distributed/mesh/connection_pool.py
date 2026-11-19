"""Connection pool — bounded reusable connection management.

Pools connections per upstream (host:port), reusing healthy ones and
recycling stale/broken ones. Tracks checkout latency, pool
exhaustion, and connection age. Enforces max lifetime and idle
timeout so leaked sockets can't accumulate.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Connection:
    conn_id: str
    upstream: str
    created_ns: int
    last_used_ns: int
    uses: int = 0
    broken: bool = False

    def age_s(self) -> float:
        return (time.time_ns() - self.created_ns) / 1e9

    def idle_s(self) -> float:
        return (time.time_ns() - self.last_used_ns) / 1e9


@dataclass
class Pool:
    upstream: str
    max_size: int = 10
    max_lifetime_s: float = 3600.0
    idle_timeout_s: float = 300.0
    available: List[Connection] = field(default_factory=list)
    checked_out: Dict[str, Connection] = field(default_factory=dict)
    total_created: int = 0
    exhaustion_events: int = 0


class ConnectionPool:
    """Per-upstream connection pooling."""

    def __init__(self, connector: Optional[Callable[[str], Any]] = None):
        self._pools: Dict[str, Pool] = {}
        self._connector = connector or (lambda upstream: {"conn": upstream})

    def _pool(self, upstream: str) -> Pool:
        return self._pools.setdefault(upstream, Pool(upstream=upstream))

    def _recycle(self, pool: Pool) -> None:
        now_ok = []
        for conn in pool.available:
            if conn.broken or conn.age_s() > pool.max_lifetime_s or conn.idle_s() > pool.idle_timeout_s:
                continue
            now_ok.append(conn)
        pool.available = now_ok

    def checkout(self, upstream: str) -> Dict[str, Any]:
        pool = self._pool(upstream)
        self._recycle(pool)
        if pool.available:
            conn = pool.available.pop()
        elif len(pool.checked_out) < pool.max_size:
            conn = Connection(
                conn_id=uuid.uuid4().hex[:10],
                upstream=upstream,
                created_ns=time.time_ns(),
                last_used_ns=time.time_ns(),
            )
            pool.total_created += 1
            self._connector(upstream)
        else:
            pool.exhaustion_events += 1
            return {"acquired": False, "reason": "pool exhausted", "upstream": upstream}
        conn.uses += 1
        conn.last_used_ns = time.time_ns()
        pool.checked_out[conn.conn_id] = conn
        return {"acquired": True, "conn_id": conn.conn_id, "reused": conn.uses > 1}

    def checkin(self, upstream: str, conn_id: str, broken: bool = False) -> bool:
        pool = self._pool(upstream)
        conn = pool.checked_out.pop(conn_id, None)
        if not conn:
            return False
        conn.broken = broken
        conn.last_used_ns = time.time_ns()
        if not broken:
            pool.available.append(conn)
        return True

    def stats(self, upstream: str) -> Dict[str, Any]:
        pool = self._pool(upstream)
        self._recycle(pool)
        return {
            "upstream": upstream,
            "available": len(pool.available),
            "checked_out": len(pool.checked_out),
            "total_created": pool.total_created,
            "exhaustion_events": pool.exhaustion_events,
            "reuse_rate": round(1 - pool.total_created / max(1, pool.total_created + len(pool.available)), 3),
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "connection-pool-card",
            "pools": {u: self.stats(u) for u in self._pools},
        }
