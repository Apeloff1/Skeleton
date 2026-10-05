"""Named extra ops as one live card. Hits increment on poke()."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.ops.act import gelu, relu
from skeleton.kernel.ops.alibi import slopes
from skeleton.kernel.ops.int4 import pack
from skeleton.kernel.ops.layernorm import layernorm
from skeleton.kernel.ops.moe import route
from skeleton.kernel.ops.residual import residual
from skeleton.kernel.ops.rope import rope
from skeleton.kernel.ops.scale import clamp, scale
from skeleton.kernel.ops.softmax import softmax
from skeleton.kernel.ops.swiglu import swiglu
from skeleton.kernel.ops.window import mask


class Extras:
    NAMES = (
        "softmax", "rope", "swiglu", "layernorm", "residual",
        "moe", "gelu", "relu", "alibi", "window", "int4", "scale", "clamp",
    )

    def __init__(self) -> None:
        self.hits: Dict[str, int] = {n: 0 for n in self.NAMES}

    def poke(self) -> Dict[str, Any]:
        x = [0.2, -0.1, 0.4, 0.0]
        softmax(x); self.hits["softmax"] += 1
        rope(x, 1); self.hits["rope"] += 1
        swiglu(x, x); self.hits["swiglu"] += 1
        layernorm(x); self.hits["layernorm"] += 1
        residual(x, x); self.hits["residual"] += 1
        route(x, k=1); self.hits["moe"] += 1
        gelu(x); self.hits["gelu"] += 1
        relu(x); self.hits["relu"] += 1
        slopes(4); self.hits["alibi"] += 1
        mask(4, 2); self.hits["window"] += 1
        pack(x); self.hits["int4"] += 1
        scale(x, 0.5); self.hits["scale"] += 1
        clamp(x); self.hits["clamp"] += 1
        return self.card()

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-extras",
            "names": list(self.NAMES),
            "hits": dict(self.hits),
            "stored_prose": 0,
        }
