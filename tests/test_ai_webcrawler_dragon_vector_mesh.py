"""Dragon vector mesh fixtures."""
from typing import Any

SVG = "image/svg+xml"
PLY = "application/x-ply"
OFF = "application/x-off"

def vector_mesh(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "vector_mesh", "size": len(data)}
