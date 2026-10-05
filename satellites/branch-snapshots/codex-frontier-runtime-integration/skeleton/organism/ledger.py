"""Append-only merkle ledger for social pointers and galaxy writes.

Each line is a hashed card. Chain is prev_sha → sha. Bodies never enter.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from skeleton.cortex.laws import check
from skeleton.organism.paths import ledger_path


def _sha(blob: str) -> str:
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def head(root: Optional[Path] = None) -> str:
    path = ledger_path(root)
    if not path.exists():
        return "0" * 64
    last = ""
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                last = line
    if not last:
        return "0" * 64
    try:
        return str(json.loads(last).get("sha") or "0" * 64)
    except json.JSONDecodeError:
        return "0" * 64


def append(event: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    payload = check({
        "kind": event.get("kind") or "organism-write",
        "at": int(time.time() * 1000),
        "decision": event.get("decision") or "",
        "url": (event.get("url") or "")[:240],
        "topic": (event.get("topic") or "")[:120],
        "G": event.get("G"),
        "atoms": (event.get("atoms") or "")[:160],
        "prev": head(root),
        "stored_prose": 0,
    })
    blob = json.dumps(payload, sort_keys=True, default=str)
    payload["sha"] = _sha(blob)
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
    return payload


def count(root: Optional[Path] = None) -> int:
    path = ledger_path(root)
    if not path.exists():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n
