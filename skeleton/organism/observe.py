"""F-2 — observe ledger. One row per runtime walk. No essays."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "observe.jsonl"


def record(org, walked: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    recall = 0.0
    try:
        from skeleton.organism.context_step import last as ctx_last
        recall = float(ctx_last(getattr(org, "root", None) if root is None else root).get("recall") or 0)
    except Exception:
        recall = 0.0
    pressure = 0.0
    try:
        from skeleton.organism.caps import card as caps_card
        pressure = float(caps_card().get("pressure") or 0)
    except Exception:
        pressure = 0.0
    row = {
        "kind": "observe",
        "G": round(float(getattr(org, "G", 0) or 0), 6),
        "steps": int(getattr(org, "steps", 0) or 0),
        "runtime_n": walked.get("n") or 0,
        "ctx_n": walked.get("ctx_n") or 0,
        "kernel_n": walked.get("kernel_n") or 0,
        "recall": recall,
        "pressure": round(pressure, 4),
        "profile": walked.get("profile"),
        "wiki": len(getattr(getattr(org.galaxy.mesh, "wiki", None), "topics", {}) or {}),
        "atoms": sum(len(getattr(lib, "shelf", {}) or {}) for lib in (org.galaxy.mesh.brains or {}).values()),
        "coverage": 0.0,
        "stored_prose": 0,
    }
    try:
        from skeleton.social.coverage import coverage_card
        row["coverage"] = coverage_card("").get("score") or 0
    except Exception:
        pass
    try:
        from skeleton.social.field import field_card
        row["field"] = field_card().get("n") or 0
    except Exception:
        row["field"] = 0
    try:
        from skeleton.organism.follow import card as follow_card
        row["follow"] = follow_card(getattr(org, "root", None)).get("n") or 0
    except Exception:
        row["follow"] = 0
    try:
        from skeleton.kernel.hot import rank
        hot = rank().get("hot") or []
        row["hot"] = hot[0] if hot else ""
    except Exception:
        row["hot"] = ""
    try:
        from skeleton.organism.helix import verify as helix_verify
        row["helix_ok"] = int(helix_verify(getattr(org, "root", None)).get("ok") or 0)
    except Exception:
        row["helix_ok"] = 1
    try:
        from skeleton.organism.chronicle.dump import inventory
        row["dumps"] = inventory(getattr(org, "root", None)).get("n") or 0
    except Exception:
        row["dumps"] = 0
    p = path(root if root is not None else getattr(org, "root", None))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def tail(n: int = 8, *, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = path(root)
    if not p.is_file():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-max(1, n):]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def card(root: Optional[Path] = None) -> Dict[str, Any]:
    rows = tail(8, root=root)
    g = [float(r.get("G") or 0) for r in rows]
    delta = (g[-1] - g[0]) if len(g) >= 2 else 0.0
    return {
        "kind": "observe",
        "n": len(rows),
        "last_G": g[-1] if g else 0,
        "delta_G": round(delta, 6),
        "last_recall": (rows[-1].get("recall") if rows else 0) or 0,
        "last_kernel_n": (rows[-1].get("kernel_n") if rows else 0) or 0,
        "wiki": (rows[-1].get("wiki") if rows else 0) or 0,
        "atoms": (rows[-1].get("atoms") if rows else 0) or 0,
        "coverage": (rows[-1].get("coverage") if rows else 0) or 0,
        "field": (rows[-1].get("field") if rows else 0) or 0,
        "follow": (rows[-1].get("follow") if rows else 0) or 0,
        "hot": (rows[-1].get("hot") if rows else "") or "",
        "helix_ok": (rows[-1].get("helix_ok") if rows else 1) or 0,
        "dumps": (rows[-1].get("dumps") if rows else 0) or 0,
        "stored_prose": 0,
    }
