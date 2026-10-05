"""Local dual-helix consensus. No network.

Sense and snap must name each other at the tip. verify() already
walks hashes. This layer adds pair agreement and a fork report.
Repair is a report, not a rewrite.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from skeleton.organism.helix import GENESIS, verify
from skeleton.organism.paths import helix_sense_path, helix_snap_path


def _tip(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    last = ""
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                last = line
    if not last:
        return {}
    try:
        return json.loads(last)
    except json.JSONDecodeError:
        return {}


def pair_ok(root: Optional[Path] = None) -> Dict[str, Any]:
    sense = _tip(helix_sense_path(root))
    snap = _tip(helix_snap_path(root))
    if not sense and not snap:
        return {"paired": 1, "why": "empty", "sense": GENESIS, "snap": GENESIS}
    s_sha = str(sense.get("sha") or GENESIS)
    p_sha = str(snap.get("sha") or GENESIS)
    s_pair = str(sense.get("pair") or GENESIS)
    p_pair = str(snap.get("pair") or GENESIS)
    ok = int(bool(sense) and bool(snap) and s_pair == p_sha and p_pair == s_sha)
    return {
        "paired": ok,
        "sense": s_sha[:12],
        "snap": p_sha[:12],
        "sense_pair": s_pair[:12],
        "snap_pair": p_pair[:12],
        "why": "pair" if ok else "fork",
    }


def agree(root: Optional[Path] = None) -> Dict[str, Any]:
    checked = verify(root)
    paired = pair_ok(root)
    ok = int(bool(checked.get("ok")) and bool(paired.get("paired")))
    return {
        "kind": "helix-consensus",
        "ok": ok,
        "verify": checked,
        "pair": paired,
        "fork": int(not ok),
        "stored_prose": 0,
    }


def repair(root: Optional[Path] = None) -> Dict[str, Any]:
    """Report only. A rewrite would invent history."""
    view = agree(root)
    view["kind"] = "helix-repair"
    view["rewritten"] = 0
    view["note"] = "report-only"
    return view
