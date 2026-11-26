"""Dragon mother glean matrix fixtures."""
from typing import Any

OWNER = "owner"
DOCUMENT = "document"
T0 = "2026-11-26T00:00:00Z"

def document(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "document", "size": len(data)}
