"""Lock manager — mutual exclusion for shared subsystem resources.

Named locks with TTL, fencing tokens, and automatic expiry. Prevents
split-brain during failover: every acquired lock carries a monotonic
fencing token that downstream writers must check. Includes deadlock
detection via wait-for graph analysis.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Lock:
    name: str
    holder: str
    token: int
    acquired_ns: int
    expires_ns: int

    def expired(self) -> bool:
        return time.time_ns() > self.expires_ns


class LockManager:
    """TTL locks with fencing tokens and deadlock detection."""

    def __init__(self, default_ttl_s: float = 30.0):
        self.default_ttl_s = default_ttl_s
        self._locks: Dict[str, Lock] = {}
        self._token_counter = 0
        self._wait_for: Dict[str, str] = {}
        self._acquire_count = 0
        self._contention_count = 0

    def _next_token(self) -> int:
        self._token_counter += 1
        return self._token_counter

    def acquire(self, name: str, holder: str, ttl_s: Optional[float] = None) -> Optional[Dict[str, Any]]:
        existing = self._locks.get(name)
        if existing and not existing.expired():
            if existing.holder == holder:
                existing.expires_ns = time.time_ns() + int((ttl_s or self.default_ttl_s) * 1e9)
                return {"name": name, "holder": holder, "token": existing.token, "refreshed": True}
            self._wait_for[holder] = name
            self._contention_count += 1
            if self._would_deadlock(holder, name):
                self._wait_for.pop(holder, None)
                raise RuntimeError(f"deadlock detected: {holder} waiting on {name}")
            return None
        token = self._next_token()
        self._locks[name] = Lock(
            name=name, holder=holder, token=token,
            acquired_ns=time.time_ns(),
            expires_ns=time.time_ns() + int((ttl_s or self.default_ttl_s) * 1e9),
        )
        self._wait_for.pop(holder, None)
        self._acquire_count += 1
        return {"name": name, "holder": holder, "token": token}

    def _would_deadlock(self, holder: str, name: str) -> bool:
        seen = {holder}
        current = self._locks.get(name)
        steps = 0
        while current and steps < 100:
            steps += 1
            if current.holder in seen:
                return True
            seen.add(current.holder)
            wanted = self._wait_for.get(current.holder)
            if not wanted:
                return False
            current = self._locks.get(wanted)
        return False

    def release(self, name: str, holder: str, token: int) -> bool:
        lock = self._locks.get(name)
        if not lock or lock.holder != holder or lock.token != token:
            return False
        del self._locks[name]
        return True

    def validate_token(self, name: str, token: int) -> bool:
        lock = self._locks.get(name)
        return bool(lock and not lock.expired() and lock.token == token)

    def force_release(self, name: str) -> bool:
        return self._locks.pop(name, None) is not None

    def sweep_expired(self) -> int:
        expired = [n for n, l in self._locks.items() if l.expired()]
        for n in expired:
            del self._locks[n]
        return len(expired)

    def card(self) -> Dict[str, Any]:
        self.sweep_expired()
        return {
            "kind": "lock-manager-card",
            "held": {n: {"holder": l.holder, "token": l.token, "expires_in_s": round((l.expires_ns - time.time_ns()) / 1e9, 1)} for n, l in self._locks.items()},
            "acquires": self._acquire_count,
            "contention_events": self._contention_count,
            "waiting": dict(self._wait_for),
        }
