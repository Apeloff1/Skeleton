from __future__ import annotations
"""Extensive structured logs for primary / secondary / tertiary math tiers."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class TierLogEntry:
    entry_id: str
    tier: str  # primary | secondary | tertiary | advanced | formal | synergy
    event: str
    ok: bool
    detail: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class TierLogger:
    def __init__(self, max_entries: int = 10000):
        self.max_entries = max_entries
        self.entries: List[TierLogEntry] = []

    def log(
        self,
        tier: str,
        event: str,
        ok: bool = True,
        detail: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ) -> TierLogEntry:
        e = TierLogEntry(
            entry_id=str(uuid.uuid4())[:10],
            tier=tier,
            event=event,
            ok=ok,
            detail=detail or {},
            duration_ms=duration_ms,
        )
        self.entries.append(e)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]
        return e

    def by_tier(self, tier: str, n: int = 50) -> List[dict]:
        rows = [e for e in self.entries if e.tier == tier]
        return [e.to_dict() for e in rows[-n:]]

    def tail(self, n: int = 50) -> List[dict]:
        return [e.to_dict() for e in self.entries[-n:]]

    def stats(self) -> Dict[str, Any]:
        by_tier: Dict[str, int] = {}
        ok_count = 0
        fail = 0
        for e in self.entries:
            by_tier[e.tier] = by_tier.get(e.tier, 0) + 1
            if e.ok:
                ok_count += 1
            else:
                fail += 1
        return {"total": len(self.entries), "ok": ok_count, "fail": fail, "by_tier": by_tier}
