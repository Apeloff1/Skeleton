"""Dragon mother glean matrix fixtures."""
from typing import Any

OWNER = "owner"
DOCUMENT = "document"
T0 = "2026-11-26T00:00:00Z"
T1 = "2026-11-26T01:00:00Z"
T2 = "2026-11-26T02:00:00Z"

def scenario(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "scenario": True}

def document(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "document", "size": len(data)}
