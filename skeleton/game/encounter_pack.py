"""Named encounter FSMs. Two-verb gates."""

from __future__ import annotations

from typing import Any


class EncounterPackError(ValueError):
    pass


NEED: dict[str, tuple[str, str]] = {
    "gate_guard": ("heat", "extract"),
    "vent_wraith": ("vent", "hide"),
    "ash_priest": ("barter", "learn"),
    "lock_smith": ("unlock", "pick"),
    "bait_seller": ("bait", "barter"),
    "coil_monk": ("coil", "ward"),
    "sleep_warden": ("sleep", "dream"),
    "fog_walker": ("fog", "listen"),
    "squad_deserter": ("talk", "hide"),
    "extract_herald": ("extract", "seal"),
    "heat_cult": ("stoke", "ward"),
    "chill_beggar": ("vent", "mend"),
    "key_thief": ("pick", "sprint"),
    "stalk_hound": ("mark", "hide"),
    "dream_echo": ("dream", "wait"),
    "save_clerk": ("save", "talk"),
    "quest_broker": ("quest", "barter"),
    "arena_ref": ("seal", "wait"),
    "monte_dealer": ("seal", "quest"),
    "shaft_rat": ("ascend", "hide"),
    "stair_dust": ("descend", "wait"),
    "jam_crowd": ("jam", "spill"),
    "quiet_monk": ("calm", "listen"),
    "loud_drum": ("sprint", "mark"),
    "hungry_forge": ("craft", "barter"),
    "fed_cook": ("mend", "wait"),
    "tracked_scout": ("mark", "sprint"),
    "hidden_cell": ("hide", "wait"),
    "pressure_valve": ("vent", "stoke"),
    "warp_ghost": ("warp", "extract"),
    "mesh_sleeper": ("handoff", "sleep"),
}


def start(name: str, seed: int) -> dict[str, Any]:
    if name not in NEED:
        raise EncounterPackError(name)
    a, b = NEED[name]
    return {"enc": name, "phase": "open", "need": [a, b], "got": [], "seed": int(seed), "done": False, "stored_prose": 0}


def step(card: dict[str, Any], verb: str) -> dict[str, Any]:
    name = str(card.get("enc") or "")
    if name not in NEED:
        raise EncounterPackError(name)
    nxt = dict(card)
    got = list(nxt.get("got") or [])
    need = list(nxt.get("need") or [])
    if nxt.get("done"):
        raise EncounterPackError("done")
    expect = need[len(got)] if len(got) < len(need) else None
    if expect is None or verb != expect:
        nxt["phase"] = "fail"
        nxt["stored_prose"] = 0
        return nxt
    got.append(verb)
    nxt["got"] = got
    nxt["done"] = got == need
    nxt["phase"] = "end" if nxt["done"] else "mid"
    nxt["stored_prose"] = 0
    return nxt


def run(name: str, seed: int, verbs: list[str]) -> dict[str, Any]:
    card = start(name, seed)
    for verb in verbs:
        card = step(card, verb)
        if card.get("phase") == "fail":
            break
    return {"kind": "encounter_pack", "enc": name, "done": bool(card.get("done")), "phase": card.get("phase"), "stored_prose": 0}
