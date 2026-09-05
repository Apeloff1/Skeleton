"""Looped-transformer kernel card. Hits increment on poke()."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.ops.etd import etd
from skeleton.kernel.ops.inject import loop_inject
from skeleton.kernel.ops.kvshare import share
from skeleton.kernel.ops.loop import unroll
from skeleton.kernel.ops.mor import mor
from skeleton.kernel.ops.overthink import run as overthink
from skeleton.kernel.ops.plt import plt
from skeleton.kernel.ops.ponder import act
from skeleton.kernel.ops.rk4 import rk4
from skeleton.kernel.ops.smelt import smelt
from skeleton.kernel.ops.scse import scse
from skeleton.kernel.ops.shortcut import shortcut
from skeleton.kernel.ops.layerloop import layerloop, stackloop
from skeleton.kernel.ops.modr import modr
from skeleton.kernel.ops.budgetr import budget
from skeleton.kernel.ops.orbit import orbit
from skeleton.kernel.ops.loopkv import run as loopkv
from skeleton.kernel.ops.schedule import run as rschedule
from skeleton.kernel.ops.thinkgate import gated
from skeleton.kernel.ops.loopscale import scaled


CITES = (
    {"topic": "smelt-moe-loop", "url": "https://arxiv.org/abs/2609.01343", "house": "arXiv"},
    {"topic": "etd-latent", "url": "https://arxiv.org/abs/2510.07358", "house": "arXiv"},
    {"topic": "plt-parallel-loop", "url": "https://arxiv.org/abs/2510.24824", "house": "arXiv"},
    {"topic": "loop-think-gen", "url": "https://arxiv.org/abs/2604.07822", "house": "arXiv"},
    {"topic": "scse-loop", "url": "https://arxiv.org/abs/2607.27656", "house": "arXiv"},
)


class Looped:
    NAMES = (
        "loop", "mor", "smelt", "etd", "plt",
        "overthink", "kvshare", "rk4", "inject", "ponder",
        "scse", "shortcut", "layerloop", "stackloop", "modr",
        "budgetr", "orbit", "loopkv", "schedule",
        "thinkgate", "loopscale",
    )

    def __init__(self) -> None:
        self.hits: Dict[str, int] = {n: 0 for n in self.NAMES}

    def poke(self) -> Dict[str, Any]:
        x = [0.2, -0.1, 0.4, 0.05]
        g = [0.3, 0.0, -0.2, 0.1]
        unroll(x, r=2); self.hits["loop"] += 1
        mor([x, g], cap=3); self.hits["mor"] += 1
        smelt(x, layers=8); self.hits["smelt"] += 1
        etd(x, enc=1, think=1, dec=1, k=2); self.hits["etd"] += 1
        plt([x, g], r=2); self.hits["plt"] += 1
        overthink(x, r_max=4); self.hits["overthink"] += 1
        share(x, r=2); self.hits["kvshare"] += 1
        rk4(x, damp=0.5); self.hits["rk4"] += 1
        loop_inject(x, r=2); self.hits["inject"] += 1
        act(x, floor=0.8, r_max=3); self.hits["ponder"] += 1
        scse(x, r=2); self.hits["scse"] += 1
        shortcut(x, r=3, skip=2); self.hits["shortcut"] += 1
        layerloop(x, layers=2, inner=2); self.hits["layerloop"] += 1
        stackloop(x, layers=2, r=2); self.hits["stackloop"] += 1
        modr(x, branches=2); self.hits["modr"] += 1
        budget(profile="mobile", want=3, halt=False); self.hits["budgetr"] += 1
        orbit(x, r=4); self.hits["orbit"] += 1
        loopkv(x, r=2, mode="share"); self.hits["loopkv"] += 1
        rschedule(x, profile="mobile"); self.hits["schedule"] += 1
        gated("why loop think"); self.hits["thinkgate"] += 1
        scaled(x, r=2); self.hits["loopscale"] += 1
        return self.card()

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-looped",
            "names": list(self.NAMES),
            "hits": dict(self.hits),
            "n": len(self.NAMES),
            "cites": [dict(c) for c in CITES],
            "law": "R=2 default; R>2 only with halt",
            "stored_prose": 0,
        }
