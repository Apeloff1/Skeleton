"""Dragon STL fixtures."""
from typing import Any

def stl(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "stl", "size": len(data)}
