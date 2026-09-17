"""Bundle world + path + kit + arena into one sealed card."""

from __future__ import annotations

from typing import Any

from skeleton.game.craft_inv import kit
from skeleton.game.floor_path import route
from skeleton.game.seal_card import seal
from skeleton.game.world_arena import compare, monte
from skeleton.game.world_tick import play


class WorldBundleError(ValueError):
    pass


def bundle(*, seed: int = 8847291) -> dict[str, Any]:
    world = play(seed=int(seed), ticks=16)
    path = route(seed=int(seed))
    bag = kit(int(seed))
    same = compare(seed_a=int(seed), seed_b=int(seed), ticks=16)
    split = compare(seed_a=int(seed), seed_b=int(seed) + 17, ticks=16)
    mc = monte(seed=int(seed), n=4, ticks=16)
    if world["extract_count"] != 1:
        raise WorldBundleError("extract")
    if not same["match"] or split["match"]:
        raise WorldBundleError("arena")
    if mc["unique_digests"] != 4:
        raise WorldBundleError("monte")
    return seal({
        "kind": "world_bundle",
        "seed": int(seed),
        "world": world["digest"],
        "path_len": path["len"],
        "coil": bag["slots"]["coil"],
        "arena_match": same["match"],
        "arena_split": split["match"],
        "monte": mc["unique_digests"],
        "extract_count": world["extract_count"],
        "warp_count": world["warp_count"],
        "sota_ready": False,
        "stored_prose": 0,
    })
