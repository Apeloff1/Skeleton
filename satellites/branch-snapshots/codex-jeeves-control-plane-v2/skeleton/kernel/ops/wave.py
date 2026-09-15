"""Wave-7 kernels — diffattn, nsa, mamba2, latentscan, mixhead, rope2."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.ops.diffattn import diffattn
from skeleton.kernel.ops.latentscan import latentscan
from skeleton.kernel.ops.mamba2 import mamba2
from skeleton.kernel.ops.mixhead import mixhead
from skeleton.kernel.ops.nsa import nsa
from skeleton.kernel.ops.rope2 import rope2


class Wave:
    NAMES = ("diffattn", "nsa", "mamba2", "latentscan", "mixhead", "rope2")

    def __init__(self) -> None:
        self.hits: Dict[str, int] = {n: 0 for n in self.NAMES}

    def poke(self) -> Dict[str, Any]:
        x = [0.2, -0.1, 0.4, 0.05]
        y = [0.1, 0.3, -0.2, 0.0]
        a = [0.9, 0.8, 0.7, 0.6]
        b = [0.1, 0.2, 0.1, 0.2]
        diffattn(x, y); self.hits["diffattn"] += 1
        nsa(x, k=2); self.hits["nsa"] += 1
        mamba2(x, a, b); self.hits["mamba2"] += 1
        latentscan(x); self.hits["latentscan"] += 1
        mixhead(x, y); self.hits["mixhead"] += 1
        rope2(x); self.hits["rope2"] += 1
        return {
            "kind": "wave",
            "n": len(self.NAMES),
            "hits": dict(self.hits),
            "ok": int(all(self.hits[n] for n in self.NAMES)),
            "stored_prose": 0,
        }
