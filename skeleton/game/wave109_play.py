"""Wave-109 play. Witness, tally, notary, attestation."""

from __future__ import annotations

from typing import Any

from skeleton.game.attestation_pack import seal as att_seal
from skeleton.game.notary_pack import attest
from skeleton.game.seal_card import seal
from skeleton.game.tally_pack import notch
from skeleton.game.wave109_index import census
from skeleton.game.witness_pack import sign


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = sign({"witness": [], "notch": 0}, "wt_00")
    state = notch(state, "ty_00")
    state = attest(state, "nt_00")
    state = att_seal(state, "at_00")
    info = census()
    return seal({
        "kind": "wave109_play",
        "seed": int(seed),
        "packs": info["n"],
        "witness": int(bool(state.get("witness"))),
        "notch": state.get("notch"),
        "sealed": state.get("sealed"),
        "sota_ready": False,
        "stored_prose": 0,
    })
