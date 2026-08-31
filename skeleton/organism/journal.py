"""Pulse journal — compact jsonl under acquired/organism/journal.jsonl.

One line per step: step, G, decision, coverage, pressure. Cap from
live atoms/8. Gitignored with the rest of acquired/organism.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.organism.paths import organism_dir


def journal_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "journal.jsonl"


def append(row: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = journal_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "step": row.get("step"),
        "G": row.get("G"),
        "decision": row.get("decision"),
        "coverage": row.get("coverage"),
        "pressure": row.get("pressure"),
        "stored_prose": 0,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, default=str) + "\n")
    trim(root=root)
    return {"path": str(path), "appended": 1}


def trim(*, root: Optional[Path] = None) -> int:
    try:
        from skeleton.organism.caps import live as live_caps
        cap = max(24, int(live_caps().atoms) // 8)
    except Exception:
        cap = 80
    path = journal_path(root)
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= cap:
        return 0
    path.write_text("\n".join(lines[-cap:]) + "\n", encoding="utf-8")
    return len(lines) - cap


def tail(n: int = 8, *, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = journal_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-max(1, n):]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
