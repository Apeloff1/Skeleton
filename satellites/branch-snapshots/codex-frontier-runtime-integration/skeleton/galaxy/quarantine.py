"""F-8 — cage low-confidence or unprovenanced atoms off the live shelf."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.galaxy.atoms import Atom

FLOOR = 0.35
RISK = 0.80


class Cage:
    def __init__(self) -> None:
        self.held: Dict[str, Atom] = {}
        self.denied = 0
        self.passed = 0

    def admit(self, atom: Atom) -> bool:
        bare = not (atom.citation or atom.url)
        low = float(atom.confidence) < FLOOR
        hot = float(atom.risk) >= RISK
        if (low and bare) or hot:
            self.held[atom.id] = atom
            self.denied += 1
            persist()
            return False
        self.passed += 1
        return True

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "galaxy-cage",
            "held": len(self.held),
            "denied": self.denied,
            "passed": self.passed,
            "stored_prose": 0,
        }


_CAGE = Cage()


def live() -> Cage:
    if not _CAGE.held and not _CAGE.denied:
        restore()
    return _CAGE


def card() -> Dict[str, Any]:
    out = _CAGE.card()
    try:
        out["mix"] = __import__("skeleton.organism.context_step", fromlist=["mix_card"]).mix_card()
    except Exception:
        out["mix"] = {"kind": "mix", "last_mix": 0, "stored_prose": 0}
    return out


def path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "cage.json"


def persist(*, root: Optional[Path] = None) -> Path:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        "kind": "galaxy-cage",
        "ids": list(_CAGE.held.keys()),
        "denied": _CAGE.denied,
        "passed": _CAGE.passed,
        "stored_prose": 0,
    }
    p.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return p


def restore(*, root: Optional[Path] = None) -> int:
    p = path(root)
    if not p.is_file():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    n = 0
    for aid in data.get("ids") or []:
        key = str(aid)
        if key and key not in _CAGE.held:
            _CAGE.held[key] = Atom.mint(
                kind="capture",
                tier="T0_FLASH",
                topic="caged",
                dialect="hold",
                brain="memory",
                color="cyan",
                confidence=0.1,
            )
            _CAGE.held[key].id = key
            n += 1
    _CAGE.denied = max(_CAGE.denied, int(data.get("denied") or n))
    _CAGE.passed = max(_CAGE.passed, int(data.get("passed") or 0))
    return n
