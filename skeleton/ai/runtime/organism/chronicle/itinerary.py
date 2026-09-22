"""Itinerary — planned codes and walked codes. Compact jsonl."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.laws import check
from skeleton.organism.chronicle.books import itinerary_path


def append(row: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = itinerary_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = check({
        "kind": "itinerary",
        "at": int(time.time() * 1000),
        "code": str(row.get("code") or "")[:40],
        "why": str(row.get("why") or "")[:80],
        "phase": str(row.get("phase") or "walk")[:20],
        "step": row.get("step"),
        "G": row.get("G"),
        "stored_prose": 0,
    })
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, sort_keys=True, default=str) + "\n")
    return line


def tail(n: int = 16, *, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = itinerary_path(root)
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-max(1, n):]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def plan(codes: List[str], *, root: Optional[Path] = None, why: str = "queue") -> Dict[str, Any]:
    wrote = 0
    for code in codes[:12]:
        append({"code": code, "why": why, "phase": "plan"}, root=root)
        wrote += 1
    return {"kind": "itinerary-plan", "n": wrote, "stored_prose": 0}
