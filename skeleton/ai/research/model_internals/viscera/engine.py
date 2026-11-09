"""Compose QK-norm, specdec, steer, quant, remat."""

from __future__ import annotations

from typing import Any

from skeleton.viscera.cards import viscera_card
from skeleton.viscera.qk_norm import qk_card
from skeleton.viscera.quant import quant_card
from skeleton.viscera.remat import remat_card
from skeleton.viscera.specdec import specdec_card
from skeleton.viscera.steer import steer_card


def _id_fwd(x):
    return [v * 1.0 for v in x]


class VisceraEngine:
    def snapshot(self) -> dict[str, Any]:
        qk = qk_card([1.0, 0.0, -1.0], [0.5, 0.5, 0.0])
        sd = specdec_card([1, 2, 3, 9], [1, 2, 3, 4])
        st = steer_card([0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
        qt = quant_card([0.1, -0.2, 0.3, -0.4])
        rm = remat_card(_id_fwd, [1.0, 2.0, 3.0])
        cards = (qk, sd, st, qt, rm)
        ok = all(c["hit"] == 1 for c in cards)
        return viscera_card(
            kind="viscera",
            hit=1 if ok else 0,
            law="viscera 2.5",
            extra={
                "accepted": sd.get("accepted"),
                "snr": qt.get("snr"),
                "identity": rm.get("identity"),
                "score": qk.get("score"),
            },
        )
