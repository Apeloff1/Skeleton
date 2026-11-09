"""Pulse journal - compact jsonl under acquired/organism/journal.jsonl.

One line per step: step, G, decision, coverage, pressure. Cap from
live atoms/8. Gitignored with the rest of acquired/organism.

Buffering is bounded by retained lines, not by bytes; reads still scan
all lines. Calls are serialized within this process. Multiple writer
processes require external coordination. Atomic replacement protects
against partial compaction, not power-loss durability of the directory.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from collections import deque
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

from skeleton.organism.paths import organism_dir


_LOCK = RLock()


def journal_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "journal.jsonl"


def append(row: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    with _LOCK:
        path = journal_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {
            "step": row.get("step"),
            "G": row.get("G"),
            "decision": row.get("decision"),
            "topic": row.get("topic"),
            "coverage": row.get("coverage"),
            "pressure": row.get("pressure"),
            "stored_prose": 0,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, default=str) + "\n")
        trim(root=root)
        return {"path": str(path), "appended": 1}


def trim(*, root: Optional[Path] = None) -> int:
    with _LOCK:
        try:
            from skeleton.organism.caps import live as live_caps
            cap = max(24, int(live_caps().atoms) // 8)
        except Exception:
            cap = 80
        path = journal_path(root)
        try:
            source = path.open("r", encoding="utf-8")
        except FileNotFoundError:
            return 0
        lines = deque(maxlen=cap)
        count = 0
        with source:
            mode = stat.S_IMODE(os.fstat(source.fileno()).st_mode)
            for line in source:
                lines.append(line.rstrip("\r\n"))
                count += 1
        if count <= cap:
            return 0
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False,
            ) as target:
                temporary = Path(target.name)
                for line in lines:
                    target.write(line + "\n")
                target.flush()
                os.chmod(target.name, mode)
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return count - cap


def tail(n: int = 8, *, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read objects in the last max(1, n) physical lines, oldest first.

    Invalid JSON and non-object values are skipped without backfilling.
    Legacy behavior for n <= 0 is retained.
    """
    with _LOCK:
        path = journal_path(root)
        try:
            source = path.open("r", encoding="utf-8")
        except FileNotFoundError:
            return []
        with source:
            lines = deque(source, maxlen=max(1, n))
        rows = []
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows
