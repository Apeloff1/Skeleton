"""Annals — cold monthly rolls. Hot journal dumps here. Ten-year horizon."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.laws import check
from skeleton.organism.chronicle.books import HORIZON_YEARS, MONTH_LINES, annals_path


def _when(ms: Optional[int] = None) -> datetime:
    if ms:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return datetime.now(timezone.utc)


def write(row: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    when = _when(row.get("at"))
    now = datetime.now(timezone.utc)
    if when.year < now.year - HORIZON_YEARS:
        return {"kind": "annals", "wrote": 0, "why": "beyond-horizon", "stored_prose": 0}
    path = annals_path(when.year, when.month, root_=root)
    line = check({
        "kind": "annals",
        "at": int(row.get("at") or time.time() * 1000),
        "year": when.year,
        "month": when.month,
        "book": str(row.get("book") or "journal")[:20],
        "topic": str(row.get("topic") or "")[:120],
        "decision": str(row.get("decision") or "")[:80],
        "code": str(row.get("code") or "")[:40],
        "G": row.get("G"),
        "sha": str(row.get("sha") or "")[:64],
        "stored_prose": 0,
    })
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, sort_keys=True, default=str) + "\n")
    return {"kind": "annals", "wrote": 1, "path": str(path), "year": when.year, "month": when.month, "stored_prose": 0}


def month_count(year: int, month: int, *, root: Optional[Path] = None) -> int:
    path = annals_path(year, month, root_=root)
    if not path.exists():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n


def full(year: int, month: int, *, root: Optional[Path] = None) -> bool:
    return month_count(year, month, root=root) >= MONTH_LINES


def years(*, root: Optional[Path] = None) -> List[int]:
    from skeleton.organism.chronicle.books import root as croot
    base = croot(root) / "annals"
    if not base.exists():
        return []
    out = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and p.name.isdigit():
            out.append(int(p.name))
    return out
