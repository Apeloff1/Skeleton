"""More named encounter FSMs."""

from __future__ import annotations

from typing import Any


class EncounterPack2Error(ValueError):
    pass


NEED: dict[str, tuple[str, str]] = {
    "ash_merchant": ("barter", "craft"),
    "vent_singer": ("vent", "listen"),
    "lock_choir": ("unlock", "talk"),
    "coil_thief": ("coil", "sprint"),
    "dream_clerk": ("dream", "save"),
    "fog_priest": ("fog", "calm"),
    "stair_guide": ("ascend", "wait"),
    "shaft_smuggler": ("descend", "barter"),
    "crowd_pusher": ("jam", "sprint"),
    "quiet_spy": ("hide", "listen"),
    "loud_herald": ("mark", "talk"),
    "seal_notary": ("seal", "save"),
    "warp_usher": ("warp", "extract"),
    "mesh_courier": ("handoff", "wait"),
    "clip_smith": ("clip", "craft"),
    "hunt_whistle": ("mark", "hide"),
    "bait_boy": ("bait", "wait"),
    "key_nun": ("pick", "unlock"),
    "sleep_guard": ("sleep", "dream"),
}


def start(name: str, seed: int) -> dict[str, Any]:
    if name not in NEED:
        raise EncounterPack2Error(name)
    a, b = NEED[name]
    return {"enc": name, "need": [a, b], "got": [], "done": False, "seed": int(seed), "stored_prose": 0}


def step(card: dict[str, Any], verb: str) -> dict[str, Any]:
    name = str(card.get("enc") or "")
    if name not in NEED:
        raise EncounterPack2Error(name)
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
