"""Audit analytics — behavioral analysis over the audit log.

Analyzes audit entries for patterns: most active actors, action
frequency trends, off-hours activity, privilege-escalation chains,
and anomalous bursts. Surfaces insider-risk signals and feeds the
security card with weekly behavior digests.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


HOUR_NS = 3_600_000_000_000
DAY_NS = 86_400_000_000_000


@dataclass
class AuditRecord:
    actor: str
    action: str
    resource: str
    timestamp_ns: int
    details: Dict[str, Any] = field(default_factory=dict)


class AuditAnalytics:
    """Behavioral analytics over audit records."""

    def __init__(self, burst_window_s: float = 300.0, burst_threshold: int = 20):
        self._records: List[AuditRecord] = []
        self.burst_window_s = burst_window_s
        self.burst_threshold = burst_threshold

    def ingest(self, actor: str, action: str, resource: str,
               timestamp_ns: Optional[int] = None,
               details: Optional[Dict[str, Any]] = None) -> AuditRecord:
        rec = AuditRecord(actor=actor, action=action, resource=resource,
                          timestamp_ns=timestamp_ns or time.time_ns(),
                          details=details or {})
        self._records.append(rec)
        if len(self._records) > 50_000:
            self._records.pop(0)
        return rec

    def actor_activity(self, since_ns: Optional[int] = None) -> Dict[str, int]:
        cutoff = since_ns or 0
        counts: Counter = Counter()
        for r in self._records:
            if r.timestamp_ns >= cutoff:
                counts[r.actor] += 1
        return dict(counts.most_common())

    def action_trends(self, bucket_s: float = 86400.0) -> Dict[str, List[int]]:
        if not self._records:
            return {}
        t0 = self._records[0].timestamp_ns
        buckets: Dict[str, Counter] = {}
        for r in self._records:
            bucket = int((r.timestamp_ns - t0) / (bucket_s * 1e9))
            buckets.setdefault(r.action, Counter())[bucket] += 1
        max_bucket = max(b for c in buckets.values() for b in c)
        return {
            action: [counts.get(i, 0) for i in range(max_bucket + 1)]
            for action, counts in buckets.items()
        }

    def off_hours_activity(self, business_hours: tuple = (8, 18)) -> List[Dict[str, Any]]:
        out = []
        for r in self._records:
            hour = (r.timestamp_ns // HOUR_NS) % 24
            if not (business_hours[0] <= hour < business_hours[1]):
                out.append({"actor": r.actor, "action": r.action, "resource": r.resource, "hour": int(hour)})
        return out

    def bursts(self) -> List[Dict[str, Any]]:
        flagged = []
        by_actor: Dict[str, List[int]] = {}
        for r in self._records:
            by_actor.setdefault(r.actor, []).append(r.timestamp_ns)
        for actor, times in by_actor.items():
            times.sort()
            for i in range(len(times)):
                j = i
                while j < len(times) and (times[j] - times[i]) / 1e9 <= self.burst_window_s:
                    j += 1
                if j - i >= self.burst_threshold:
                    flagged.append({
                        "actor": actor,
                        "actions": j - i,
                        "window_s": self.burst_window_s,
                        "start_ns": times[i],
                    })
                    break
        return flagged

    def escalation_chains(self) -> List[Dict[str, Any]]:
        chains = []
        for r in self._records:
            if r.action in ("grant", "rbac.grant") and r.details.get("role") in ("admin", "operator"):
                if r.details.get("actor") == r.actor or r.details.get("granted_by") == r.actor:
                    chains.append({
                        "actor": r.actor,
                        "role": r.details.get("role"),
                        "self_grant": True,
                        "timestamp_ns": r.timestamp_ns,
                    })
        return chains

    def digest(self, window_s: float = 604800.0) -> Dict[str, Any]:
        cutoff = time.time_ns() - int(window_s * 1e9)
        recent = [r for r in self._records if r.timestamp_ns >= cutoff]
        return {
            "records": len(recent),
            "top_actors": dict(Counter(r.actor for r in recent).most_common(5)),
            "top_actions": dict(Counter(r.action for r in recent).most_common(5)),
            "top_resources": dict(Counter(r.resource for r in recent).most_common(5)),
            "off_hours_count": len(self.off_hours_activity()),
            "bursts": self.bursts(),
            "escalations": self.escalation_chains(),
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "audit-analytics-card",
            "total_records": len(self._records),
            "weekly_digest": self.digest(),
        }
