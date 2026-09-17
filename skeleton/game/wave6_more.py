"""Second wave-6 pass. Watch, badge, permit, cache, cord."""

from __future__ import annotations

from typing import Any

from skeleton.game.badge_pack import pin
from skeleton.game.cache_pack import hide
from skeleton.game.cord_pack import tie
from skeleton.game.permit_pack import issue
from skeleton.game.seal_card import seal
from skeleton.game.watch_pack import post


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state: dict[str, Any] = {
        "alert": 0,
        "badge": [],
        "permit": [],
        "cache": {},
        "cord": {},
        "room": "f0r0",
    }
    state = post(state, "wt_00", "f0r1")
    state = pin(state, "bd_00")
    state = issue(state, "pm_00")
    state = hide(state, "cc_00", "scrap", 2)
    state = tie(state, "cd_00", "f0r0", "f0r1")
    return seal({
        "kind": "wave6_more",
        "seed": int(seed),
        "watch": state.get("watch"),
        "badge": int(bool(state.get("badge"))),
        "permit": int(bool(state.get("permit"))),
        "cache": int(((state.get("cache") or {}).get("cc_00") or {}).get("scrap", 0)),
        "cord": int(bool(state.get("cord"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
