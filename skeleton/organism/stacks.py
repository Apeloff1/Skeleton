"""Stacks — last card from every plane. No DAG walk."""
from __future__ import annotations

from typing import Any, Dict, Optional
from pathlib import Path


def _read(root: Optional[Path], name: str) -> Dict[str, Any]:
    import json
    base = Path(root) if root else Path(".")
    p = base / "chronicle" / name
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def card(root: Optional[Path] = None) -> Dict[str, Any]:
    def _get(mod, fn, *a):
        try:
            m = __import__(mod, fromlist=[fn])
            return getattr(m, fn)(*a)
        except Exception:
            return {}

    obs = _get("skeleton.organism.observe", "card", root)
    rt = _get("skeleton.organism.runtime", "last", root)
    ctx = _get("skeleton.organism.context_step", "last", root)
    cal = _get("skeleton.organism.calendar", "card", root)
    cage = _get("skeleton.galaxy.quarantine", "card")
    cov = _get("skeleton.social.coverage", "coverage_card", "")
    field = _get("skeleton.social.field", "field_card")
    hot = _get("skeleton.kernel.hot", "rank")
    board = _get("skeleton.kernel.scoreboard", "card")
    caps = _get("skeleton.organism.caps", "card")
    return {
        "kind": "stacks",
        "organism": {"runtime_n": rt.get("n"), "ctx_n": ctx.get("n"), "observe_n": obs.get("n"), "G": obs.get("last_G")},
        "kernel": {"kernel_n": obs.get("last_kernel_n") or rt.get("kernel_n"), "hot": hot.get("hot"), "board_n": board.get("n"), "profile": caps.get("tier") or rt.get("profile")},
        "galaxy": {"wiki": obs.get("wiki"), "atoms": obs.get("atoms"), "cage": cage.get("denied")},
        "social": {"coverage": cov.get("score") or obs.get("coverage"), "field": field.get("n") or obs.get("field")},
        "chronicle": {"dumps": obs.get("dumps"), "years": cal.get("years")},
        "memory": {"recall": obs.get("last_recall"), "helix_ok": obs.get("helix_ok")},
        "editor": {"conductor": _read(root, "conductor.json").get("code")},
        "stored_prose": 0,
    }
