"""Dragon WebP fixtures."""
from typing import Any

def vp8x(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "webp", "size": len(data)}
