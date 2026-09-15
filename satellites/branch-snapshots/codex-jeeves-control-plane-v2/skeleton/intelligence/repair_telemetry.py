"""Fault-tolerant repair telemetry and diagnostics.

Provides detailed telemetry capture for every repair attempt,
including timing, resource usage, error recovery, and
operator-visible diagnostic cards.
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RepairTelemetry:
    """Detailed telemetry for a single repair attempt."""
    surface: str
    pass_n: int
    start_at: int
    end_at: int
    duration_ms: int
    before_score: float
    after_score: float
    action_count: int
    accepted: bool
    reason: str
    error: str = ""
    stack_trace: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "pass_n": self.pass_n,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "duration_ms": self.duration_ms,
            "before_score": round(self.before_score, 4),
            "after_score": round(self.after_score, 4),
            "delta": round(self.after_score - self.before_score, 4),
            "action_count": self.action_count,
            "accepted": self.accepted,
            "reason": self.reason,
            "error": self.error,
            "stack_trace": self.stack_trace,
            "metadata": self.metadata,
        }


def _telemetry_path(root=None) -> Path:
    from skeleton.organism.paths import organism_dir
    return organism_dir(root) / "repair_telemetry.jsonl"


def capture_telemetry(
    surface: str,
    pass_n: int,
    start_at: int,
    result: Dict[str, Any],
    error: Optional[Exception] = None,
    metadata: Optional[Dict[str, Any]] = None,
    root=None,
) -> RepairTelemetry:
    """Capture telemetry for a repair attempt. Call this after
    every repair pass, successful or failed."""
    end_at = int(time.time() * 1000)
    before_score = float((result.get("before") or {}).get("score") or 0.0)
    after_score = float((result.get("after") or {}).get("score") or before_score)
    actions = list(result.get("actions") or [])
    accepted = bool(result.get("ok") or result.get("accepted"))
    reason = str(result.get("reason") or "unknown")

    error_str = ""
    stack = ""
    if error is not None:
        error_str = str(error)
        stack = traceback.format_exc()

    telemetry = RepairTelemetry(
        surface=surface,
        pass_n=pass_n,
        start_at=start_at,
        end_at=end_at,
        duration_ms=end_at - start_at,
        before_score=before_score,
        after_score=after_score,
        action_count=len(actions),
        accepted=accepted,
        reason=reason,
        error=error_str,
        stack_trace=stack,
        metadata=metadata or {},
    )

    path = _telemetry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(telemetry.to_dict(), sort_keys=True, default=str) + "\n")

    # Trim
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 512:
            path.write_text("\n".join(lines[-512:]) + "\n", encoding="utf-8")

    return telemetry


def load_telemetry(root=None, surface: str = "", limit: int = 32) -> List[Dict[str, Any]]:
    """Load recent telemetry records."""
    path = _telemetry_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            row = json.loads(line)
            if not surface or row.get("surface") == surface:
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def telemetry_card(surface: str = "", *, root=None, limit: int = 16) -> Dict[str, Any]:
    """Operator-facing telemetry card."""
    rows = load_telemetry(root=root, surface=surface, limit=limit)
    if not rows:
        return {"kind": "repair-telemetry-card", "surface": surface or "all", "n": 0, "avg_duration_ms": 0, "error_rate": 0.0, "stored_prose": 0}
    durations = [r.get("duration_ms", 0) for r in rows]
    errors = [r for r in rows if r.get("error")]
    accepted = [r for r in rows if r.get("accepted")]
    return {
        "kind": "repair-telemetry-card",
        "surface": surface or "all",
        "n": len(rows),
        "avg_duration_ms": round(sum(durations) / max(1, len(durations)), 1),
        "max_duration_ms": max(durations) if durations else 0,
        "error_rate": round(len(errors) / len(rows), 4),
        "accept_rate": round(len(accepted) / len(rows), 4),
        "recent": rows[-8:],
        "stored_prose": 0,
    }


def error_summary(surface: str = "", *, root=None, limit: int = 64) -> Dict[str, Any]:
    """Summarize repair errors by type and frequency."""
    rows = load_telemetry(root=root, surface=surface, limit=limit)
    errors = [r for r in rows if r.get("error")]
    if not errors:
        return {"kind": "repair-error-summary", "surface": surface or "all", "total_errors": 0, "by_type": {}, "stored_prose": 0}
    by_type: Dict[str, int] = {}
    for e in errors:
        err_type = e.get("error", "unknown")[:80]
        by_type[err_type] = by_type.get(err_type, 0) + 1
    return {
        "kind": "repair-error-summary",
        "surface": surface or "all",
        "total_errors": len(errors),
        "by_type": by_type,
        "most_common": max(by_type, key=by_type.get) if by_type else "",
        "stored_prose": 0,
    }
