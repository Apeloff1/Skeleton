"""Operator-facing quality state helpers.

Provides a compact rollup shape so product, nervous, doctor, and satellites
can speak about quality in one vocabulary even when only some subsystems
have emitted explicit quality reports so far.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from skeleton.organism.paths import quality_path


def summarize_quality(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = [dict(x) for x in items if x]
    if not rows:
        return {
            "kind": "quality-rollup",
            "count": 0,
            "accepted": 0,
            "rejected": 0,
            "accept_rate": 0.0,
            "weakest": "",
            "reasons": {},
        }
    accepted = sum(1 for x in rows if x.get("accepted"))
    rejected = len(rows) - accepted
    weakest = min(rows, key=lambda x: float(x.get("score", 0.0) or 0.0))
    reasons: Dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason") or "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "kind": "quality-rollup",
        "count": len(rows),
        "accepted": accepted,
        "rejected": rejected,
        "accept_rate": round(accepted / max(1, len(rows)), 4),
        "weakest": weakest.get("weakest_path") or weakest.get("path") or "",
        "reasons": reasons,
    }


def quality_pressure(rollup: Dict[str, Any]) -> float:
    rejected = int(rollup.get("rejected") or 0)
    count = int(rollup.get("count") or 0)
    return round(rejected / max(1, count), 4)


def append_quality(entry: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = quality_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": int(time.time() * 1000),
        "kind": str(entry.get("kind") or "quality"),
        "surface": str(entry.get("surface") or entry.get("pipeline") or "unknown"),
        "accepted": bool(entry.get("accepted")),
        "reason": str(entry.get("reason") or "unknown"),
        "score": float(entry.get("score") or 0.0),
        "weakest_path": str(entry.get("weakest_path") or ""),
        "summary": dict(entry.get("summary") or {}),
        "metadata": dict(entry.get("metadata") or {}),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    trim_quality(root=root)
    return row


def trim_quality(*, root: Optional[Path] = None, cap: int = 256) -> int:
    path = quality_path(root)
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= cap:
        return 0
    path.write_text("\n".join(lines[-cap:]) + "\n", encoding="utf-8")
    return len(lines) - cap


def load_quality(*, root: Optional[Path] = None, limit: int = 32) -> List[Dict[str, Any]]:
    path = quality_path(root)
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def latest_quality(*, root: Optional[Path] = None) -> Dict[str, Any]:
    rows = load_quality(root=root, limit=1)
    return rows[-1] if rows else {}


def quality_snapshot(*, root: Optional[Path] = None, limit: int = 32) -> Dict[str, Any]:
    rows = load_quality(root=root, limit=limit)
    return {
        "latest": rows[-1] if rows else {},
        "recent": rows,
        "rollup": summarize_quality(rows),
    }
