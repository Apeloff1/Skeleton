"""Second wave-5 pass. Ammo, rumor, cargo, contract, tool, ward, oath."""

from __future__ import annotations

from typing import Any

from skeleton.game.ammo_pack import fire, load
from skeleton.game.cargo_pack import load as cargo_load
from skeleton.game.contract_pack import open_ct, tick_ct
from skeleton.game.oath_pack import swear
from skeleton.game.rumor_pack import hear
from skeleton.game.seal_card import seal
from skeleton.game.tool_pack import own, use
from skeleton.game.ward_pack import raise_ward


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state: dict[str, Any] = {
        "ammo": {},
        "rumor": [],
        "cargo": [],
        "tools": [],
        "coil": 2,
        "heat": 8,
        "xp": 4,
        "oath": [],
    }
    state = load(state, "slug", 2)
    state = fire(state, "slug")
    state = hear(state, "ru_00")
    state = cargo_load(state, "cg_00")
    state = own(state, "torch")
    state = use(state, "torch")
    state = raise_ward(state, "wd_00")
    state = swear(state, "oh_00")
    ct = tick_ct(open_ct("ct_00", int(seed)), state)
    return seal({
        "kind": "wave5_more",
        "seed": int(seed),
        "ammo": int((state.get("ammo") or {}).get("slug", 0)),
        "rumor": int(bool(state.get("rumor"))),
        "cargo": len(list(state.get("cargo") or [])),
        "tool": state.get("last_tool"),
        "ward": state.get("ward"),
        "oath": int(bool(state.get("oath"))),
        "ct_done": int(bool(ct.get("done"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
