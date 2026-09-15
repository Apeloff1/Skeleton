"""Loop fire log — chronicle/loop.jsonl. One line per think-gate decision."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def path(root: Optional[Path] = None) -> Path:
    if root is None:
        try:
            from skeleton.organism.paths import organism_root
            root = organism_root()
        except Exception:
            root = Path(".")
    p = Path(root or ".") / "chronicle" / "loop.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(row: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    out = {
        "kind": "loop-log",
        "open": int(row.get("open") or 0),
        "fire": int(row.get("fire") or 0),
        "family": str(row.get("family") or ""),
        "r": int(row.get("r") or 0),
        "stored_prose": 0,
    }
    try:
        p = path(root)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, separators=(",", ":")) + "\n")
        out["log"] = 1
    except Exception:
        out["log"] = 0
    return out


def tail(n: int = 16, *, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = path(root)
    if not p.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        for line in lines[-max(1, int(n)):]:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        return []
    return rows


def card(root: Optional[Path] = None) -> Dict[str, Any]:
    rows = tail(32, root=root)
    opened = sum(1 for r in rows if int(r.get("open") or 0))
    fired = sum(1 for r in rows if int(r.get("fire") or 0))
    last = rows[-1] if rows else {}
    return {
        "kind": "loop-log",
        "n": len(rows),
        "opened": opened,
        "fired": fired,
        "last_open": int(last.get("open") or 0),
        "last_fire": int(last.get("fire") or 0),
        "last_family": last.get("family") or "",
        "stored_prose": 0,
    }
