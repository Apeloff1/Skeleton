"""Wave-14 play. Glass, bench, mist, pot."""

from __future__ import annotations

from typing import Any

from skeleton.game.bench_pack import set_bench
from skeleton.game.glass_pack import set_pane
from skeleton.game.mist_pack import spray
from skeleton.game.pot_pack import plant
from skeleton.game.seal_card import seal
from skeleton.game.wave14_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_pane({"wet": 0}, "gl_00")
    node = set_bench(node, "bn_00")
    node = spray(node, "mi_00")
    state = plant({"pot": {}}, "pt_00", "stock_a")
    info = census()
    return seal({
        "kind": "wave14_play",
        "seed": int(seed),
        "packs": info["n"],
        "glass": int(bool(node.get("glass"))),
        "bench": node.get("bench"),
        "pot": int(bool(state.get("pot"))),
        "wet": node.get("wet"),
        "sota_ready": False,
        "stored_prose": 0,
    })
