"""Parallel latent thoughts engine — design specification (data only).

This module previously contained a bare JSON document, which is not valid
importable Python (``true`` is undefined). The same specification is now an
immutable Python constant; no behaviour is implied beyond the description.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

PARALLEL_LATENT_THOUGHTS_ENGINE: Mapping[str, Any] = MappingProxyType({
    "parallel_latent_thoughts_engine": MappingProxyType({
        "description": "Engine for generating and managing multiple parallel latent thoughts during looped reasoning.",
        "mechanics": MappingProxyType({
            "stream_count": "configurable (default 4)",
            "cross_stream_attention": True,
            "synthesis_step": "at end of each iteration",
            "integration": "Used inside Advanced Looped Transformer and high-effort reasoning modes",
        }),
    }),
})

__all__ = ["PARALLEL_LATENT_THOUGHTS_ENGINE"]
