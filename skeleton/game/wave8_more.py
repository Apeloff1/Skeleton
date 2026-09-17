"""Second wave-8 pass. Ore, flux, ingot, batch, hearth."""

from __future__ import annotations

from typing import Any

from skeleton.game.batch_pack import start as batch_start
from skeleton.game.flux_pack import add as flux_add
from skeleton.game.hearth_pack import lite
from skeleton.game.ingot_pack import cast
from skeleton.game.ore_pack import dig
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state: dict[str, Any] = {"ore": {}, "flux": [], "ingot": [], "heat": 6}
    state = dig(state, "or_00")
    state = flux_add(state, "fx_00")
    state = cast(state, "ig_00")
    state = batch_start(state, "bh_00")
    node = lite({"heat": int(state.get("heat", 0))}, "ht_00")
    return seal({
        "kind": "wave8_more",
        "seed": int(seed),
        "ore": int(bool(state.get("ore"))),
        "flux": int(bool(state.get("flux"))),
        "ingot": int(bool(state.get("ingot"))),
        "batch": state.get("batch"),
        "hearth": node.get("hearth"),
        "sota_ready": False,
        "stored_prose": 0,
    })
