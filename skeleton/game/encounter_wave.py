"""Wave-4 encounter FSMs."""

from __future__ import annotations

from typing import Any


class EncounterWaveError(ValueError):
    pass


NEED: dict[str, tuple[str, str]] = {
    f"enc_{i:02d}": (
        ("heat", "vent", "hide", "talk", "wait", "mark")[i % 6],
        ("extract", "seal", "sprint", "barter", "dream", "calm")[i % 6],
    )
    for i in range(24)
}


def start(name: str, seed: int) -> dict[str, Any]:
    if name not in NEED:
        raise EncounterWaveError(name)
    a, b = NEED[name]
    return {"enc": name, "need": [a, b], "got": [], "done": False, "seed": int(seed), "stored_prose": 0}


def step(card: dict[str, Any], verb: str) -> dict[str, Any]:
    name = str(card.get("enc") or "")
    if name not in NEED:
        raise EncounterWaveError(name)
    nxt = dict(card)
    got = list(nxt.get("got") or [])
    need = list(nxt.get("need") or [])
    expect = need[len(got)] if len(got) < len(need) else None
    if expect is None or verb != expect:
        nxt["phase"] = "fail"
        nxt["stored_prose"] = 0
        return nxt
    got.append(verb)
    nxt["got"] = got
    nxt["done"] = got == need
    nxt["stored_prose"] = 0
    return nxt
