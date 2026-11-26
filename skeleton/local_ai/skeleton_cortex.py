"""
Work the Skeleton cortex and CommandDeck without clobbering the operator aggregator. Organs, hive merkle, LoRA house-copy, clipped-G, era_bind, Queue-12 kernels.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

ORGANS = ["hive", "lora", "clipped_g", "era_bind", "queue12"]


def process(data: dict) -> dict:
    refused = admit("skeleton_cortex", data)
    if refused:
        return refused
    organ = data.get("organ")
    if organ is None:
        return stamp("skeleton_cortex", data, {"organs": ORGANS})
    if organ not in ORGANS:
        return {
            "ok": False,
            "error": "unknown organ",
            "card": "skeleton_cortex",
            "organs": list(ORGANS),
        }
    return stamp("skeleton_cortex", data, {"organs": ORGANS, "organ": organ})
