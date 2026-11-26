"""Dragon archive grant fixtures."""
from typing import Any

source = "stub-source"
snapshot = {"ok": True, "snapshot": True}
CHECKPOINT = "checkpoint"
SID = "sid"
SCOPE = {"tenant_id": "tenant", "owner_id": "owner"}

def archive_grant_fixture(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "archive": True}
