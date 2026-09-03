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


class Catalog:
    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-catalog",
            "obligatory": list(OBLIGATORY),
            "extra": list(EXTRA),
            "n": len(OBLIGATORY) + len(EXTRA),
            "stored_prose": 0,
        }
