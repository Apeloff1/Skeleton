"""F-8 — cage low-confidence or unprovenanced atoms off the live shelf."""
from __future__ import annotations

from typing import Any, Dict, List

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
    return _CAGE


def card() -> Dict[str, Any]:
    return _CAGE.card()
