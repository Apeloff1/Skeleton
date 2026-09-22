"""Decade — seasons until a cap. Horizon metaphor, not a clock."""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.kernel.season import run as season_run


def run(text: str = "plan tensor ttk", *, seasons: int = 3, walk_n: int = 2) -> Dict[str, Any]:
    seasons = max(1, min(10, int(seasons)))
    walk_n = max(1, min(4, int(walk_n)))
    rows: List[Dict[str, Any]] = []
    stopped = ""
    for i in range(seasons):
        row = season_run(text, n=walk_n)
        rows.append({"i": i, "walks": row.get("walks"), "stopped": row.get("stopped")})
        if row.get("stopped"):
            stopped = str(row.get("stopped"))
            break
    return {
        "kind": "kernel-decade",
        "seasons": len(rows),
        "asked": seasons,
        "walk_n": walk_n,
        "rows": rows,
        "stopped": stopped,
        "stored_prose": 0,
    }
