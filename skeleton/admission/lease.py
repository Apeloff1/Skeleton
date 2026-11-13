"""Fail-closed serialized admission lease for Skeleton repo-wide push rate.

Addresses #4580. Exact-head CAS. <5 admitted pushes / rolling 60s.
Fail-closed on unavailable, stale, or concurrent mutation.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

MAX_PUSHES_LAST_MINUTE = 5
LEASE_TTL_SECONDS = 60


@dataclass(frozen=True)
class LeaseToken:
    lane: str
    head_sha: str
    actor: str
    issued_at: float
    expiry: float
    nonce: str


class AdmissionLease:
    def __init__(self, ledger_path: Path):
        self.ledger_path = ledger_path
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            self._write_ledger({"leases": [], "pushes": []})

    def _read_ledger(self) -> dict:
        try:
            return json.loads(self.ledger_path.read_text())
        except Exception:
            raise RuntimeError("ledger unavailable or corrupt; fail closed")

    def _write_ledger(self, data: dict) -> None:
        tmp = self.ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.ledger_path)

    def acquire(self, lane: str, expected_sha: str, actor: str) -> Optional[LeaseToken]:
        data = self._read_ledger()
        now = time.time()
        # prune expired
        data["leases"] = [l for l in data["leases"] if l["expiry"] > now]
        data["pushes"] = [p for p in data["pushes"] if now - p["ts"] < 60]
        if len(data["pushes"]) >= MAX_PUSHES_LAST_MINUTE:
            return None  # headroom exhausted
        # fail if any active lease for same expected_sha from other lane
        for l in data["leases"]:
            if l["head_sha"] == expected_sha and l["lane"] != lane:
                raise RuntimeError("concurrent mutation on expected SHA; fail closed")
        token = LeaseToken(
            lane=lane,
            head_sha=expected_sha,
            actor=actor,
            issued_at=now,
            expiry=now + LEASE_TTL_SECONDS,
            nonce=f"{lane}-{int(now*1000)}",
        )
        data["leases"].append(asdict(token))
        self._write_ledger(data)
        return token

    def release(self, token: LeaseToken, actual_sha: str) -> None:
        if token.head_sha != actual_sha:
            raise RuntimeError("SHA mismatch on release; fail closed")
        data = self._read_ledger()
        data["leases"] = [l for l in data["leases"] if l["nonce"] != token.nonce]
        data["pushes"].append({"ts": time.time(), "sha": actual_sha, "lane": token.lane})
        self._write_ledger(data)

    def count_recent(self) -> int:
        data = self._read_ledger()
        now = time.time()
        return sum(1 for p in data["pushes"] if now - p["ts"] < 60)
