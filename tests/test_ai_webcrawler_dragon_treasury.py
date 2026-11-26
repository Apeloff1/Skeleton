"""Dragon treasury fixtures."""
from typing import Any

obs = {"ok": True, "observed": True}
A = "a"
B = "b"
C = "c"
NOW = "2026-11-26T00:00:00Z"
DAY = "2026-11-26"
BASE = "https://example.com"
SCOPE = {"tenant_id": "tenant", "owner_id": "owner"}

def treasury_fixture(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "treasury": True}
