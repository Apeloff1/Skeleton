"""F-3 — rot assess the composed scope queue before enact."""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.memory.rot_guard import ContextRotGuard

_GUARD = ContextRotGuard(attention_budget=48, watch_at=0.35, rot_at=0.55)


def assess(queue: List[str], *, constraints: tuple = ("STORED_PROSE 0", "HOUSE DIALECT")) -> Dict[str, Any]:
    prompt = "\n".join(list(constraints) + [str(c) for c in queue])
    report = _GUARD.assess(prompt, constraints=constraints)
    card = report.to_dict()
    card["kind"] = "scope-rot"
    card["stored_prose"] = 0
    return card


def trim(queue: List[str], rot: Dict[str, Any]) -> List[str]:
    if str(rot.get("verdict") or "") != "rot":
        return queue
    keep = [c for c in queue if c in {"pulse", "dream", "dump", "doctor"}]
    return keep or queue[:1]


def card() -> Dict[str, Any]:
    st = _GUARD.stats()
    st["kind"] = "scope-rot-stats"
    st["stored_prose"] = 0
    return st


def persist(rot: Dict[str, Any], *, root=None):
    import json
    from pathlib import Path
    base = Path(root) if root else Path(".")
    p = base / "chronicle" / "rot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        "kind": "scope-rot",
        "verdict": rot.get("verdict"),
        "risk": rot.get("risk"),
        "checks": _GUARD.checks,
        "rot_events": _GUARD.rot_events,
        "stored_prose": 0,
    }
    p.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return p
