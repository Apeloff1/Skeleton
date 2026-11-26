"""Dragon TAR fixtures."""
from typing import Any

def tar(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "tar", "size": len(data)}
