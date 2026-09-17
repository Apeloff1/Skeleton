"""Verb law table. Preconditions, heat delta, fail-closed."""

from __future__ import annotations

from typing import Any


class VerbLawError(ValueError):
    pass


DELTAS = {
    "heat": 2, "sleep": -3, "dream": -1, "wake": 0, "extract": -8, "warp": -8,
    "scavenge": 1, "craft": 1, "bait": 1, "unlock": 0, "enter": 0, "inject": 3,
    "wait": -1, "move": 0, "attack": 1, "defend": 0, "buy": 0, "grant_xp": 0,
    "patrol": 0, "chase": 1, "retreat": 0, "hide": -1, "mark": 0, "calm": -1,
    "trade": 0, "rest": -2, "pulse": 1, "forge": 2, "clip": 0, "observe": 0,
    "cut": 0, "stamp": 0, "compose": 0, "play": 0, "hunt": 1, "scan": 0,
    "diffuse": 1, "weave": 0, "solve": 0, "detect": 0, "mutate": 1, "shift": 0,
    "climb": 1, "drop": 0,
}


def pre(state: dict[str, Any], verb: str) -> None:
    if not isinstance(state, dict):
        raise VerbLawError("state")
    name = str(verb or "").strip().lower()
    if name in {"extract", "warp"}:
        if int(state.get("extracted", 0)) >= 1:
            raise VerbLawError(f"{name} once")
        if int(state.get("heat", 0)) < 8:
            raise VerbLawError(f"{name} needs heat")
    elif name == "dream" and int(state.get("sleep", 0)) < 8 and int(state.get("slept", 0)) < 1:
        raise VerbLawError("dream needs sleep")
    elif name == "craft" and int(state.get("scrap", 0)) < 1:
        raise VerbLawError("craft scrap")
    elif name == "unlock" and not state.get("locked", False) and not state.get("lock", False):
        raise VerbLawError("not locked")


def apply_verb(state: dict[str, Any], verb: str) -> dict[str, Any]:
    name = str(verb or "").strip().lower()
    if name not in DELTAS:
        raise VerbLawError(f"unknown verb {verb}")
    pre(state, name)
    nxt = dict(state)
    nxt["heat"] = max(0, min(100, int(nxt.get("heat", 0)) + DELTAS[name]))
    if name == "extract":
        nxt["extracted"] = int(nxt.get("extracted", 0)) + 1
        nxt["warp_count"] = 1
    elif name == "scavenge":
        nxt["scrap"] = int(nxt.get("scrap", 0)) + 1
    elif name == "craft":
        nxt["scrap"] = max(0, int(nxt.get("scrap", 0)) - 1)
        nxt["parts"] = int(nxt.get("parts", 0)) + 1
    elif name == "sleep":
        nxt["sleep"] = min(100, int(nxt.get("sleep", 0)) + 8)
        nxt["slept"] = int(nxt.get("slept", 0)) + 1
    elif name == "dream":
        nxt["dreams"] = int(nxt.get("dreams", 0)) + 1
    elif name == "unlock":
        nxt["locked"] = False
        nxt["key"] = 1
    elif name == "bait":
        nxt["threat"] = int(nxt.get("threat", 0)) + 2
    nxt["last_verb"] = name
    nxt["stored_prose"] = 0
    return nxt


def run_script(state: dict[str, Any], verbs: list[str]) -> dict[str, Any]:
    cur = dict(state)
    frames = [dict(cur)]
    for verb in verbs:
        try:
            cur = apply_verb(cur, verb)
        except VerbLawError:
            if verb != "wait":
                try:
                    cur = apply_verb(cur, "wait")
                except VerbLawError:
                    pass
        frames.append(dict(cur))
    return {"kind": "verb_run", "n": len(verbs), "final": cur, "frames": len(frames), "stored_prose": 0}
