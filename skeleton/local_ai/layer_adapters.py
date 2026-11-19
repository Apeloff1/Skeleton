"""
Promote Viscera, Graphs, Sheaf, Spine, Motive, and Primitives into Skeleton as thin facades with lineage docs and tests. Never copy artifact trees.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

LAYERS = ["Viscera", "Graphs", "Sheaf", "Spine", "Motive", "Primitives"]


def process(data: dict) -> dict:
    refused = admit("layer_adapters", data)
    if refused:
        return refused
    layer = data.get("layer")
    if layer is None:
        return stamp("layer_adapters", data, {"layers": LAYERS})
    if layer not in LAYERS:
        return {
            "ok": False,
            "error": "unknown layer",
            "card": "layer_adapters",
            "layers": list(LAYERS),
        }
    return stamp("layer_adapters", data, {"layers": LAYERS, "layer": layer})
