"""Obscure + superfluous kernel card. Hits increment on poke()."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.ops.bitnet import bitlinear, ternarize
from skeleton.kernel.ops.dry import dry, presence
from skeleton.kernel.ops.earlyexit import halt
from skeleton.kernel.ops.geglu import geglu, reglue, silu, sqrelu
from skeleton.kernel.ops.hadamard import hadamard
from skeleton.kernel.ops.minp import min_p, typical
from skeleton.kernel.ops.mla import mla
from skeleton.kernel.ops.qknorm import qk_clip, qk_norm
from skeleton.kernel.ops.sink import with_sink
from skeleton.kernel.ops.softcap import softcap
from skeleton.kernel.ops.ssm import scan, step
from skeleton.kernel.ops.yarn import ntk, xpos, yarn


class Obscure:
    NAMES = (
        "geglu", "reglue", "sqrelu", "silu",
        "qknorm", "qkclip", "softcap",
        "yarn", "ntk", "xpos",
        "sink", "minp", "typical",
        "mla", "ssm", "bitnet", "hadamard",
        "earlyexit", "dry", "presence",
    )

    def __init__(self) -> None:
        self.hits: Dict[str, int] = {n: 0 for n in self.NAMES}

    def poke(self) -> Dict[str, Any]:
        x = [0.2, -0.1, 0.4, 0.05]
        g = [0.3, 0.0, -0.2, 0.1]
        geglu(x, g); self.hits["geglu"] += 1
        reglue(x, g); self.hits["reglue"] += 1
        sqrelu(x); self.hits["sqrelu"] += 1
        silu(x); self.hits["silu"] += 1
        qk_norm(x, g); self.hits["qknorm"] += 1
        qk_clip(x); self.hits["qkclip"] += 1
        softcap(x); self.hits["softcap"] += 1
        yarn(x, 3); self.hits["yarn"] += 1
        ntk(x, 3); self.hits["ntk"] += 1
        xpos(x, 3); self.hits["xpos"] += 1
        with_sink([(x, g), (g, x), (x, x)], window=1); self.hits["sink"] += 1
        min_p(x); self.hits["minp"] += 1
        typical(x); self.hits["typical"] += 1
        mla(x, [(x, g), (g, x)]); self.hits["mla"] += 1
        scan([x, g]); self.hits["ssm"] += 1
        step(x, g); self.hits["ssm"] += 0
        W = [ternarize(x), ternarize(g)]
        bitlinear(x, W); self.hits["bitnet"] += 1
        hadamard(x); self.hits["hadamard"] += 1
        halt(x); self.hits["earlyexit"] += 1
        dry(x, [1]); self.hits["dry"] += 1
        presence(x, [0]); self.hits["presence"] += 1
        return self.card()

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-obscure",
            "names": list(self.NAMES),
            "hits": dict(self.hits),
            "n": len(self.NAMES),
            "stored_prose": 0,
        }
