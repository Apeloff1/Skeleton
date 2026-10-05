"""Follow-state — the organism learns the operator's token bag.

Rolodex topics + journal tails + last stimuli. No prose bodies.
Used as a bias, not a planner. Grows with the house.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.laws import check
from skeleton.galaxy.atoms import token_set
from skeleton.organism.paths import organism_dir

BAG_CAP = 64


def _path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "follow.json"


def _empty() -> Dict[str, Any]:
    return {"kind": "follow", "bag": {}, "seen": 0, "handle": "house", "stored_prose": 0}


def load(root: Optional[Path] = None) -> Dict[str, Any]:
    path = _path(root)
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty()
    data.setdefault("bag", {})
    data.setdefault("seen", 0)
    data.setdefault("stored_prose", 0)
    return data


def save(card: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = check(card)
    path.write_text(json.dumps(clean, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return clean


def _trim(bag: Dict[str, int]) -> Dict[str, int]:
    if len(bag) <= BAG_CAP:
        return bag
    keep = sorted(bag.items(), key=lambda kv: (-kv[1], kv[0]))[:BAG_CAP]
    return {k: v for k, v in keep}


def grow(text: str, *, root: Optional[Path] = None, handle: str = "") -> Dict[str, Any]:
    card = load(root)
    bag = dict(card.get("bag") or {})
    for tok in token_set(text or ""):
        if len(tok) < 3:
            continue
        bag[tok] = int(bag.get(tok) or 0) + 1
    try:
        from skeleton.organism.chronicle.rolodex import load as rolo_load
        rolo = rolo_load(root)
        card["handle"] = handle or (rolo.get("self") or {}).get("handle") or card.get("handle")
        for topic in (rolo.get("topics") or {}):
            for tok in token_set(str(topic)):
                if len(tok) >= 3:
                    bag[tok] = int(bag.get(tok) or 0) + 1
    except Exception:
        pass
    card["bag"] = _trim(bag)
    card["seen"] = int(card.get("seen") or 0) + 1
    card["kind"] = "follow"
    card["stored_prose"] = 0
    return save(card, root=root)


def bias(text: str, *, root: Optional[Path] = None) -> float:
    bag = load(root).get("bag") or {}
    src = set(token_set(text or ""))
    if not src or not bag:
        return 0.0
    keys = set(bag)
    return round(len(src & keys) / len(src | keys), 4)


def card(root: Optional[Path] = None) -> Dict[str, Any]:
    data = load(root)
    top: List[str] = [k for k, _ in sorted((data.get("bag") or {}).items(), key=lambda kv: -kv[1])[:12]]
    return {
        "kind": "follow",
        "handle": data.get("handle"),
        "seen": data.get("seen"),
        "bag_n": len(data.get("bag") or {}),
        "top": top,
        "mix": __import__("skeleton.organism.context_step", fromlist=["mix_card"]).mix_card(root),
        "stored_prose": 0,
    }
