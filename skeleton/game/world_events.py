"""Named world events. Table-driven start/tick/end."""

from __future__ import annotations

from typing import Any


class WorldEventError(ValueError):
    pass


EVENTS = (
    "vent_surge", "ash_fall", "fog_wall", "shaft_rattle", "lock_click",
    "key_glint", "scrap_spill", "forge_flare", "sleep_bell", "dream_ripple",
    "extract_hum", "stalker_howl", "squad_split", "bait_drop", "coil_spark",
    "token_tick", "heat_bloom", "chill_front", "bridge_creak", "dead_whisper",
    "cycle_echo", "stair_dust", "spawn_pulse", "patrol_swap", "chase_bark",
    "retreat_scuff", "alert_rise", "calm_break", "quest_chime", "barter_tap",
    "skill_click", "save_stamp", "fog_thin", "climate_flip", "cell_jam",
    "occupancy_spike", "pressure_peak", "los_cut", "warp_pre", "warp_post",
    "digest_seal", "era_bind", "mass_clip", "doctor_nudge", "arena_split",
    "replay_fork", "handoff_mark", "mesh_sleep",
)


def start(name: str, seed: int) -> dict[str, Any]:
    if name not in EVENTS:
        raise WorldEventError(name)
    return {
        "event": name,
        "phase": "start",
        "heat": EVENTS.index(name) % 8,
        "seed": int(seed),
        "t": 0,
        "stored_prose": 0,
    }


def tick(card: dict[str, Any], t: int) -> dict[str, Any]:
    name = str(card.get("event") or "")
    if name not in EVENTS:
        raise WorldEventError(name)
    nxt = dict(card)
    nxt["t"] = int(t)
    nxt["phase"] = "tick"
    delta = (EVENTS.index(name) % 7) - 3
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + delta))
    nxt["stored_prose"] = 0
    return nxt


def end(card: dict[str, Any]) -> dict[str, Any]:
    name = str(card.get("event") or "")
    if name not in EVENTS:
        raise WorldEventError(name)
    nxt = dict(card)
    nxt["phase"] = "end"
    nxt["done"] = True
    nxt["stored_prose"] = 0
    return nxt


def run(name: str, seed: int, ticks: int = 4) -> dict[str, Any]:
    card = start(name, seed)
    frames = [dict(card)]
    for t in range(int(ticks)):
        card = tick(card, t)
        frames.append(dict(card))
    card = end(card)
    frames.append(dict(card))
    return {"kind": "world_event_run", "event": name, "n": len(frames), "final": card, "stored_prose": 0}
