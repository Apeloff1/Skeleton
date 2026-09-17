"""Wave-8 play. Bellows, anvil, kiln, bloom, quench."""

from __future__ import annotations

from typing import Any

from skeleton.game.anvil_pack import set_anvil
from skeleton.game.bellows_pack import pump
from skeleton.game.bloom_pack import draw
from skeleton.game.kiln_pack import fire
from skeleton.game.quench_pack import dip
from skeleton.game.seal_card import seal
from skeleton.game.wave8_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = pump({"heat": 6}, "bw_00")
    node = set_anvil(node, "av_00")
    node = fire(node, "kn_00")
    state: dict[str, Any] = {"heat": int(node.get("heat", 0)), "bloom": []}
    state = draw(state, "bm_00")
    state = dip(state, "qn_00")
    info = census()
    return seal({
        "kind": "wave8_play",
        "seed": int(seed),
        "packs": info["n"],
        "anvil": node.get("anvil"),
        "bloom": int(bool(state.get("bloom"))),
        "heat": state.get("heat"),
        "sota_ready": False,
        "stored_prose": 0,
    })
