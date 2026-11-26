"""Dragon ICO fixtures."""
from typing import Any

def ico(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "ico", "size": len(data)}
