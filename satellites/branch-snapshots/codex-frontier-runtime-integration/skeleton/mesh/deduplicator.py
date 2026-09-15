"""Request deduplicator — idempotency for inbound operations.

Assigns every mutating request an idempotency key; identical keys
within the retention window return the cached original response
instead of re-executing. Detects conflicting replays (same key,
different payload) and rejects them, exactly like Stripe-style
idempotency. Essential for safe retries across the mesh.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class IdempotencyRecord:
    key: str
    payload_hash: str
    response: Any
    status: str
    created_ns: int


class Deduplicator:
    """Idempotency-key request deduplication."""

    def __init__(self, retention_s: float = 86400.0):
        self.retention_s = retention_s
        self._records: Dict[str, IdempotencyRecord] = {}
        self._hits = 0
        self._conflicts = 0

    def _hash_payload(self, payload: Dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def _sweep(self) -> None:
        cutoff = time.time_ns() - int(self.retention_s * 1e9)
        expired = [k for k, r in self._records.items() if r.created_ns < cutoff]
        for k in expired:
            del self._records[k]

    def execute(self, key: str, payload: Dict[str, Any],
                fn: Callable[[], Any]) -> Dict[str, Any]:
        self._sweep()
        payload_hash = self._hash_payload(payload)
        existing = self._records.get(key)
        if existing:
            if existing.payload_hash != payload_hash:
                self._conflicts += 1
                return {
                    "executed": False,
                    "conflict": True,
                    "reason": "idempotency key reused with different payload",
                }
            self._hits += 1
            return {
                "executed": False,
                "replay": True,
                "response": existing.response,
            }
        self._records[key] = IdempotencyRecord(
            key=key, payload_hash=payload_hash, response=None,
            status="in_progress", created_ns=time.time_ns(),
        )
        try:
            response = fn()
        except Exception:
            del self._records[key]
            raise
        self._records[key] = IdempotencyRecord(
            key=key, payload_hash=payload_hash, response=response,
            status="completed", created_ns=time.time_ns(),
        )
        return {"executed": True, "response": response}

    def check(self, key: str) -> Optional[Dict[str, Any]]:
        self._sweep()
        record = self._records.get(key)
        if not record:
            return None
        return {"status": record.status, "payload_hash": record.payload_hash, "has_response": record.response is not None}

    def card(self) -> Dict[str, Any]:
        self._sweep()
        return {
            "kind": "deduplicator-card",
            "records": len(self._records),
            "replay_hits": self._hits,
            "conflicts": self._conflicts,
            "in_progress": len([r for r in self._records.values() if r.status == "in_progress"]),
        }
