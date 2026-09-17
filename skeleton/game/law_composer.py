"""Law composer. Status + verb + encounter + quest + extract ledger."""

from __future__ import annotations

from typing import Any

from skeleton.game.climate_pack import run as climate_run
from skeleton.game.encounter_pack import run as enc_run
from skeleton.game.extract_ledger import play as ledger_play
from skeleton.game.floors import weave_campus
from skeleton.game.quest_pack import run as quest_run
from skeleton.game.seal_card import seal
from skeleton.game.status_laws import apply as status_apply
from skeleton.game.status_laws import tick_named
from skeleton.game.verb_pack import run as verb_run


class LawComposerError(ValueError):
    pass


def play(*, seed: int = 8847291) -> dict[str, Any]:
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    weather = climate_run(campus["nodes"], 8, "vent")
    state: dict[str, Any] = {
        "heat": int(weather["peak"]),
        "sleep": 8,
        "scrap": 4,
        "parts": 2,
        "tokens": 12,
        "extracted": 0,
        "xp": 8,
        "status": {},
    }
    state = status_apply(state, "burn", 2)
    state = tick_named(state)
    try:
        state = verb_run(state, ["stoke", "wait", "stoke"])
    except Exception:
        pass
    enc = enc_run("extract_herald", int(seed), ["extract", "seal"])
    quest = quest_run("stoke_heat", int(seed), state)
    led = ledger_play(seed=int(seed))
    return seal({
        "kind": "law_composer",
        "seed": int(seed),
        "peak": weather["peak"],
        "enc_done": enc["done"],
        "quest_done": quest["done"],
        "ledger": led["extract_count"],
        "extract_count": led["extract_count"],
        "warp_count": led["warp_count"],
        "sota_ready": False,
        "stored_prose": 0,
    })
