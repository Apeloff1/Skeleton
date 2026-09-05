"""Multiple stimulus rotors. Each axis advances alone.

House, topic, depth, think, obscure. One pulse ticks one rotor
(round-robin) so the field does not freeze on a single pointer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

AXES = ("house", "topic", "depth", "think", "obscure")

THINK_CUES = (
    "why derive this",
    "how does the loop halt",
    "reason about depth",
    "proof of residual scale",
    "latent recurrent plan",
)

DEPTH_CUES = ("R=1", "R=2", "R=3 halt", "smelt mid", "etd think")


def path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    p = base / "chronicle" / "rotors.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load(root: Optional[Path] = None) -> Dict[str, Any]:
    p = path(root)
    if not p.is_file():
        return {"kind": "rotors", "i": 0, "axis": {a: 0 for a in AXES}, "stored_prose": 0}
    try:
        row = json.loads(p.read_text(encoding="utf-8"))
        row.setdefault("axis", {a: 0 for a in AXES})
        for a in AXES:
            row["axis"].setdefault(a, 0)
        return row
    except Exception:
        return {"kind": "rotors", "i": 0, "axis": {a: 0 for a in AXES}, "stored_prose": 0}


def save(row: Dict[str, Any], root: Optional[Path] = None) -> None:
    path(root).write_text(json.dumps(row, indent=2), encoding="utf-8")


def _houses() -> List[str]:
    from skeleton.organism.fieldwalk import HOUSE_ORDER
    return list(HOUSE_ORDER)


def _topics() -> List[Dict[str, str]]:
    from skeleton.social.sources import SOTA_POINTERS
    return list(SOTA_POINTERS)


def _obscure() -> List[str]:
    from skeleton.kernel.ops.catalog import OBSCURE
    return list(OBSCURE)


def tick(root: Optional[Path] = None, *, explicit: str = "") -> Dict[str, Any]:
    state = load(root)
    i = int(state.get("i") or 0)
    axis = AXES[i % len(AXES)]
    state["axis"][axis] = int(state["axis"].get(axis) or 0) + 1
    state["i"] = i + 1
    state["last"] = axis
    cue = compose(state, explicit=explicit)
    state["cue"] = cue
    state["kind"] = "rotors"
    state["stored_prose"] = 0
    save(state, root)
    return state


def compose(state: Dict[str, Any], *, explicit: str = "") -> str:
    ax = state.get("axis") or {}
    houses = _houses()
    topics = _topics()
    obs = _obscure()
    h = houses[int(ax.get("house") or 0) % len(houses)] if houses else "arXiv"
    t = topics[int(ax.get("topic") or 0) % len(topics)] if topics else {"topic": "plan", "url": ""}
    d = DEPTH_CUES[int(ax.get("depth") or 0) % len(DEPTH_CUES)]
    th = THINK_CUES[int(ax.get("think") or 0) % len(THINK_CUES)]
    o = obs[int(ax.get("obscure") or 0) % len(obs)] if obs else "yarn"
    user = str(explicit or "").strip()
    parts = [user, th, d, o, h, t.get("topic") or "", t.get("url") or ""]
    return " ".join(p for p in parts if p)


def card(root: Optional[Path] = None) -> Dict[str, Any]:
    state = load(root)
    return {
        "kind": "rotors",
        "i": int(state.get("i") or 0),
        "last": state.get("last") or "",
        "axis": dict(state.get("axis") or {}),
        "cue": state.get("cue") or "",
        "n": len(AXES),
        "stored_prose": 0,
    }
