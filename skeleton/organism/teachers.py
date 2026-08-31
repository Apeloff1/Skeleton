"""Teacher contact inside an organismer step.

Weights stay on the mouth (LoRA+SGD+Hebb+absorb). The galaxy only
receives a principle atom: magnitude, slot names, citation. Fail-closed.
No import-time HuggingFace. No teacher prose on the shelf.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.cortex.contact import is_teacher


def slots_of(neo) -> List[str]:
    found = []
    for slot, port in (getattr(neo, "slots", {}) or {}).items():
        if is_teacher(port):
            found.append(str(slot))
    return found


def sync(neo, stimulus: str) -> Dict[str, Any]:
    if neo is None or not hasattr(neo, "contact"):
        return {"contacted": 0, "reason": "no-mouth", "stored_prose": 0}
    names = slots_of(neo)
    if not names:
        return {"contacted": 0, "reason": "no-teacher", "slots": [], "stored_prose": 0}
    cards = []
    for slot in names:
        try:
            cards.append(neo.contact(slot, stimulus))
        except Exception as exc:
            cards.append({"contacted": 0, "slot": slot, "error": type(exc).__name__})
    mags = [float(c.get("magnitude") or 0) for c in cards if c.get("contacted")]
    return {
        "contacted": sum(1 for c in cards if c.get("contacted")),
        "slots": names,
        "magnitude": round(max(mags) if mags else 1.0, 4),
        "cards": cards,
        "stored_prose": 0,
    }


def glean_rule(galaxy, *, stimulus: str, contact: Dict[str, Any], genos: Dict[str, Any] | None = None):
    mag = float((contact or {}).get("magnitude") or (genos or {}).get("M") or 1.0)
    slots = ",".join((contact or {}).get("slots") or [])
    dialect = f"contact-rule mag {mag:.4f} slots {slots or 'none'} house"
    atom = galaxy.distiller.glean(dialect, citation="house:contact")
    return atom.to_dict() if atom is not None else None
