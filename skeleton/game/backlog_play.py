"""Run the landed backlog packs as one sealed play."""

from __future__ import annotations

from typing import Any

from skeleton.game.backlog_tables import census as bag_census
from skeleton.game.craft_pack import craft
from skeleton.game.door_pack import make as door_make
from skeleton.game.door_pack import use as door_use
from skeleton.game.encounter_wave import start as enc_start
from skeleton.game.encounter_wave import step as enc_step
from skeleton.game.extract_ledger import ExtractLedgerError, record as extract_once
from skeleton.game.floors import weave_campus
from skeleton.game.heat_sources import emit as heat_emit
from skeleton.game.inventory import empty
from skeleton.game.lock_patterns import open_lock
from skeleton.game.quest_wave import open_quest, tick_quest
from skeleton.game.seal_card import seal
from skeleton.game.skill_pack import learn as skill_learn
from skeleton.game.wave4_index import census as wave_census
from skeleton.game.weather_cells import tick as weather_tick


class BacklogPlayError(ValueError):
    pass


def play(*, seed: int = 8847291) -> dict[str, Any]:
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    nodes = [weather_tick("wx_00", dict(n), 3) for n in campus["nodes"]]
    nodes = [heat_emit("src_00", n) for n in nodes]
    peak = max(int(n.get("heat", 0)) for n in nodes)

    state: dict[str, Any] = {
        "key": 4,
        "heat": peak,
        "sleep": 8,
        "xp": 16,
        "scrap": 4,
        "parts": 2,
        "extracted": 0,
        "skills": [],
    }
    inv = empty()
    inv["scrap"] = 4
    inv["parts"] = 2

    opened = 0
    try:
        state = open_lock("lock_00", state)
        opened += 1
    except Exception:
        pass
    door, state = door_use(door_make("wood"), state)
    if door.get("open"):
        opened += 1
    try:
        inv, state = craft("coil", inv, state)
        crafted = 1
    except Exception:
        crafted = 0
    try:
        state = skill_learn(state, "heat_ward")
        skilled = 1
    except Exception:
        skilled = 0

    quest = tick_quest(open_quest("q_00", int(seed)), state)
    enc = enc_start("enc_00", int(seed))
    enc = enc_step(enc, "heat")
    enc = enc_step(enc, "extract")

    extracted = 0
    if int(state.get("heat", 0)) >= 8:
        try:
            extract_once(state)
            extracted = 1
            state["extracted"] = 1
            state["warp_count"] = 1
        except ExtractLedgerError:
            extracted = int(state.get("extracted", 0))

    bags = bag_census()
    waves = wave_census()
    return seal({
        "kind": "backlog_play",
        "seed": int(seed),
        "packs": int(waves.get("n", 0)),
        "bag": sum(int(v) for k, v in bags.items() if k != "stored_prose"),
        "opened": opened,
        "crafted": crafted,
        "skilled": skilled,
        "quest_done": int(bool(quest.get("done"))),
        "enc_done": int(bool(enc.get("done"))),
        "peak": peak,
        "extract_count": extracted,
        "warp_count": int(state.get("warp_count", 0)),
        "sota_ready": False,
        "stored_prose": 0,
    })
