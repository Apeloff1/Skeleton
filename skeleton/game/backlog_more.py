"""Second backlog pass. Fog, save, role, buff, status."""

from __future__ import annotations

from typing import Any

from skeleton.game.buff_wave import on as buff_on
from skeleton.game.fog_pack import apply as fog_apply
from skeleton.game.role_pack import step as role_step
from skeleton.game.save_pack import blank, write as save_write
from skeleton.game.seal_card import seal
from skeleton.game.status_wave import apply as status_apply
from skeleton.game.status_wave import tick as status_tick


def play(*, seed: int = 8847291, digest: str = "") -> dict[str, Any]:
    state: dict[str, Any] = {"alert": 1, "heat": 8, "los_pen": 0, "status": {}, "buff": {}}
    state = fog_apply(state, "thin", 3)
    state = buff_on(state, "buf_00")
    state = status_apply(state, "frost", 2)
    state = status_tick(state, "frost")
    hunter = {"role": "scout", "room": "f0r0", "alert": 0, "seen": 0}
    hunter = role_step(hunter, "f0r1", {"f0r0": "f0r1"}, 1)
    bank = save_write(blank(), "slot0", {"digest": digest or "x", "kind": "backlog_more", "extract_count": 0})
    return seal({
        "kind": "backlog_more",
        "seed": int(seed),
        "fog": state.get("fog_bank"),
        "los": state.get("los_pen"),
        "buff": int(bool((state.get("buff") or {}).get("buf_00"))),
        "frost": int((state.get("status") or {}).get("frost", 0)),
        "role": hunter.get("role"),
        "saved": int(bool(bank.get("slot0"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
