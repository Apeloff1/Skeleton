"""Dragon GLB fixtures."""
from typing import Any

def glb(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "glb", "size": len(data)}
