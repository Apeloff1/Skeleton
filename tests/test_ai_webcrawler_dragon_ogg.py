"""Dragon OGG fixtures."""
from typing import Any

def opus(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "ogg", "size": len(data)}
