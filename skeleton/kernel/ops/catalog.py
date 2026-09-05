"""Obligatory vs extra kernel catalog."""
from __future__ import annotations

from typing import Any, Dict, Tuple

OBLIGATORY: Tuple[str, ...] = (
    "matmul", "attention", "rmsnorm", "kvcache", "qlinear", "sample", "fused",
    "gpu", "ram",
)

EXTRA: Tuple[str, ...] = (
    "softmax", "rope", "swiglu", "embed", "layernorm", "residual",
    "moe", "dma", "gather", "pipeline", "breaker", "bulkhead",
    "gelu", "relu", "alibi", "window", "int4", "check", "stock",
    "block", "stock_live", "scale", "clamp",
)

OBSCURE: Tuple[str, ...] = (
    "geglu", "reglue", "sqrelu", "silu",
    "qknorm", "qkclip", "softcap",
    "yarn", "ntk", "xpos",
    "sink", "minp", "typical",
    "mla", "ssm", "bitnet", "hadamard",
    "earlyexit", "dry", "presence",
)

SOCIAL: Tuple[str, ...] = (
    "linattn", "xquant", "fp8kv", "pagekv",
    "flashdec", "specdec", "mtp", "gqa", "sparseattn",
    "treeattn", "chunkprefill", "ragged", "prefixhash",
    "marlin", "onlinesm", "packgqa", "persistkv",
    "cascade", "megafuse", "kselect",
)

LOOPED: Tuple[str, ...] = (
    "loop", "mor", "smelt", "etd", "plt",
    "overthink", "kvshare", "rk4", "inject", "ponder",
    "scse", "shortcut", "layerloop", "stackloop", "modr",
    "budgetr", "orbit", "loopkv", "schedule",
    "thinkgate", "loopscale", "haltmix", "loopfuse",
)


class Catalog:
    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-catalog",
            "obligatory": list(OBLIGATORY),
            "extra": list(EXTRA),
            "obscure": list(OBSCURE),
            "social": list(SOCIAL),
            "looped": list(LOOPED),
            "n": len(OBLIGATORY) + len(EXTRA) + len(OBSCURE) + len(SOCIAL) + len(LOOPED),
            "stored_prose": 0,
        }
