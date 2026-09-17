"""Second wave-109 pass. Extra witness + attest."""

from __future__ import annotations

from typing import Any

from skeleton.game.notary_pack import attest
from skeleton.game.seal_card import seal
from skeleton.game.witness_pack import sign


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = sign({"witness": []}, "wt_01")
    state = attest(state, "nt_01")
    return seal({
        "kind": "wave109_more",
        "seed": int(seed),
        "witness": int(bool(state.get("witness"))),
        "ok": state.get("ok"),
        "sota_ready": False,
        "stored_prose": 0,
    })
