"""Stub for dragon vector mesh fixtures."""
from typing import Any
SVG = "svg"
PLY = "ply"
OFF = "off"
def vector_mesh(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "vector_mesh"}
