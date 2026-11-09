"""Persistent KV pages — keep hot blocks across pulses.

Cite: persistentkv-page field pointer. Decade dump, not RAM leak.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]


def path(root=None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "persistkv.json"


def save(slots: List[Tuple[Row, Row]], *, root=None, cap: int = 16) -> dict:
    keep = slots[-max(1, int(cap)) :]
    slim = [{"k": k, "v": v} for k, v in keep]
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"n": len(slim), "rows": slim, "stored_prose": 0}), encoding="utf-8")
    bump(len(slim))
    return {"kind": "persist-kv", "n": len(slim), "stored_prose": 0}


def load(root=None) -> List[Tuple[Row, Row]]:
    p = path(root)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in data.get("rows") or []:
        out.append((list(r.get("k") or []), list(r.get("v") or [])))
    bump(len(out))
    return out
