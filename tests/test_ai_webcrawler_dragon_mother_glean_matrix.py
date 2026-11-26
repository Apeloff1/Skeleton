"""Dragon mother glean matrix fixtures."""
from typing import Any

OWNER = "owner"
DOCUMENT = "document"

def document(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "document", "size": len(data)}
