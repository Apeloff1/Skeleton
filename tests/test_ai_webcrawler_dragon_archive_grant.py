"""Stub for dragon archive grant fixtures."""
from typing import Any

source = "stub-source"
snapshot = {"ok": True}
CHECKPOINT = "checkpoint"
SID = "sid"

def archive_grant_fixture(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "archive": True}
