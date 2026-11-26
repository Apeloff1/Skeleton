"""Dragon MP4 fixtures."""
from typing import Any

def movie(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "mp4", "size": len(data)}
