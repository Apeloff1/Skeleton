"""Encounter FSM. Shared stepper plus named starts."""

from __future__ import annotations

from typing import Any


class EncounterError(ValueError):
    pass


NAMES = (
    "stalker_door", "heat_vent", "scrap_pile", "forge_spark", "sleep_trap",
    "dream_echo", "lock_puzzle", "extract_gate", "bait_lure", "patrol_cross",
    "coil_short", "barter_stall", "quest_mark", "warp_shimmer", "fog_bank",
    "bridge_crack", "dead_end", "cycle_loop", "shaft_drop", "key_glint",
    "status_cloud", "squad_howl", "token_chime", "clip_press",
)


def start(name: str, seed: int) -> dict[str, Any]:
    if name not in NAMES:
        raise EncounterError(name)
    return {
        "enc": name,
        "state": "idle",
        "heat": NAMES.index(name) % 8,
        "seed": int(seed),
        "ticks": 0,
        "stored_prose": 0,
    }


def step(card: dict[str, Any], verb: str) -> dict[str, Any]:
    nxt = dict(card)
    nxt["ticks"] = int(nxt.get("ticks", 0)) + 1
    state = str(nxt.get("state") or "idle")
    v = str(verb or "").strip().lower()
    if state == "idle" and v in {"heat", "scavenge", "move", "enter"}:
        nxt["state"] = "warn"
        nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    elif state == "warn" and v in {"attack", "craft", "unlock", "extract"}:
        nxt["state"] = "engage"
    elif state == "warn" and v == "wait":
        nxt["state"] = "fade"
    elif state == "engage" and v in {"attack", "craft", "extract"}:
        nxt["state"] = "resolve"
        nxt["won"] = True
    elif state == "engage" and v == "retreat":
        nxt["state"] = "fade"
        nxt["won"] = False
    elif state == "resolve":
        nxt["state"] = "fade"
        nxt["done"] = True
    elif state == "fade":
        nxt["state"] = "idle"
        nxt["heat"] = max(0, int(nxt.get("heat", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt


def run(name: str, seed: int, verbs: list[str]) -> dict[str, Any]:
    card = start(name, seed)
    frames = [dict(card)]
    for verb in verbs:
        card = step(card, verb)
        frames.append(dict(card))
    return {"kind": "encounter_run", "enc": name, "n": len(frames), "final": card, "stored_prose": 0}
