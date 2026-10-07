"""Error taxonomy — unified error classification and fingerprinting.

Classifies every error into a stable taxonomy (category, severity,
retryability, owner subsystem) and fingerprints occurrences so the
same root error aggregates across noise. Produces top-error reports,
novelty detection (new fingerprints), and trend deltas for doctor.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


CATEGORIES = {
    "timeout": {"severity": "warning", "retryable": True},
    "connection": {"severity": "warning", "retryable": True},
    "permission": {"severity": "error", "retryable": False},
    "validation": {"severity": "info", "retryable": False},
    "not_found": {"severity": "info", "retryable": False},
    "resource_exhausted": {"severity": "error", "retryable": True},
    "internal": {"severity": "critical", "retryable": False},
    "dependency": {"severity": "error", "retryable": True},
    "unknown": {"severity": "warning", "retryable": False},
}


@dataclass
class ErrorOccurrence:
    fingerprint: str
    category: str
    subsystem: str
    message: str
    count: int = 1
    first_seen_ns: int = 0
    last_seen_ns: int = 0


class ErrorTaxonomy:
    """Error classification with fingerprint aggregation."""

    def __init__(self, novelty_window_s: float = 3600.0):
        self._occurrences: Dict[str, ErrorOccurrence] = {}
        self.novelty_window_s = novelty_window_s
        self._history: List[Dict[str, Any]] = []

    def classify(self, exc: Exception) -> str:
        name = type(exc).__name__.lower()
        msg = str(exc).lower()
        if "timeout" in name or "timed out" in msg:
            return "timeout"
        if "connection" in name or "refused" in msg or "unreachable" in msg:
            return "connection"
        if "permission" in name or "forbidden" in msg or "denied" in msg:
            return "permission"
        if "value" in name or "type" in name or "invalid" in msg:
            return "validation"
        if "notfound" in name or "not found" in msg or "keyerror" in name:
            return "not_found"
        if "memory" in name or "quota" in msg or "exhausted" in msg:
            return "resource_exhausted"
        if "dependency" in msg or "upstream" in msg or "downstream" in msg:
            return "dependency"
        if "internal" in name or "runtime" in name:
            return "internal"
        return "unknown"

    def fingerprint(self, subsystem: str, exc: Exception) -> str:
        template = re.sub(r"\d+", "N", str(exc))[:120]
        raw = f"{subsystem}:{type(exc).__name__}:{template}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def record(self, subsystem: str, exc: Exception) -> ErrorOccurrence:
        fp = self.fingerprint(subsystem, exc)
        category = self.classify(exc)
        now = time.time_ns()
        occ = self._occurrences.get(fp)
        if occ:
            occ.count += 1
            occ.last_seen_ns = now
        else:
            occ = ErrorOccurrence(
                fingerprint=fp, category=category, subsystem=subsystem,
                message=str(exc)[:200], first_seen_ns=now, last_seen_ns=now,
            )
            self._occurrences[fp] = occ
        self._history.append({"fingerprint": fp, "category": category, "subsystem": subsystem, "timestamp_ns": now})
        if len(self._history) > 5000:
            self._history.pop(0)
        return occ

    def top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        ranked = sorted(self._occurrences.values(), key=lambda o: -o.count)
        return [{
            "fingerprint": o.fingerprint,
            "category": o.category,
            "subsystem": o.subsystem,
            "count": o.count,
            "message": o.message,
            "severity": CATEGORIES[o.category]["severity"],
            "retryable": CATEGORIES[o.category]["retryable"],
        } for o in ranked[:limit]]

    def novel_errors(self) -> List[Dict[str, Any]]:
        cutoff = time.time_ns() - int(self.novelty_window_s * 1e9)
        return [{
            "fingerprint": o.fingerprint,
            "category": o.category,
            "subsystem": o.subsystem,
            "message": o.message,
            "count": o.count,
        } for o in self._occurrences.values() if o.first_seen_ns >= cutoff]

    def category_rollup(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for o in self._occurrences.values():
            out[o.category] = out.get(o.category, 0) + o.count
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "error-taxonomy-card",
            "unique_fingerprints": len(self._occurrences),
            "total_occurrences": sum(o.count for o in self._occurrences.values()),
            "categories": self.category_rollup(),
            "novel_count": len(self.novel_errors()),
            "top": self.top_errors(5),
        }
