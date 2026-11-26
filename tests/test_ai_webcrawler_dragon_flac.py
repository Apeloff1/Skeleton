"""Dragon FLAC fixtures."""
from typing import Any

def flac(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "flac", "size": len(data)}
