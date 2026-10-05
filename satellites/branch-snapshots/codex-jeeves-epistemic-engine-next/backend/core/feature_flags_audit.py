"""
core/feature_flags_audit.py — mutation audit log.

Every POST/DELETE on /api/feature-flags writes a row here so we can:
  * answer "who toggled X, when?"
  * replay history in a debug session
  * surface a 'changed by …' badge in the admin UI

The collection is intentionally small + capped-feeling — we keep the most
recent 5000 entries on a TTL/size best-effort basis. No PII beyond IP +
User-Agent (already in nginx logs anyway).
"""
from __future__ import annotations

import time
from typing import Any

from core.databases import core_db

COLLECTION = "feature_flags_audit"
MAX_ROWS = 5000


async def log_change(
    *,
    name: str,
    action: str,                # "upsert" | "delete"
    diff: dict[str, Any] | None,
    ip: str | None,
    user_agent: str | None,
    actor: str | None = None,
) -> None:
    """Append a single audit row. Never raises."""
    try:
        doc = {
            "ts": time.time(),
            "name": name,
            "action": action,
            "diff": diff or {},
            "ip": ip or "",
            "user_agent": (user_agent or "")[:200],
            "actor": actor or "",
        }
        await core_db[COLLECTION].insert_one(doc)
        # Best-effort cap: prune oldest if we exceed MAX_ROWS.
        count = await core_db[COLLECTION].estimated_document_count()
        if count > MAX_ROWS:
            # Delete oldest 10% in one shot to amortise.
            cur = core_db[COLLECTION].find({}, {"_id": 1}).sort("ts", 1).limit(int(MAX_ROWS * 0.1))
            ids = [d["_id"] async for d in cur]
            if ids:
                await core_db[COLLECTION].delete_many({"_id": {"$in": ids}})
    except Exception as e:  # noqa: BLE001
        print(f"[feature_flags_audit] log_change error: {type(e).__name__}: {e}", flush=True)


async def recent(limit: int = 100, name: str | None = None) -> list[dict[str, Any]]:
    """Return the N most-recent audit rows (newest first), optionally filtered by flag."""
    try:
        q = {"name": name} if name else {}
        cur = core_db[COLLECTION].find(q).sort("ts", -1).limit(min(max(limit, 1), 500))
        rows = [d async for d in cur]
        for r in rows:
            r.pop("_id", None)
        return rows
    except Exception as e:  # noqa: BLE001
        print(f"[feature_flags_audit] recent error: {type(e).__name__}: {e}", flush=True)
        return []


async def stats() -> dict[str, Any]:
    try:
        total = await core_db[COLLECTION].estimated_document_count()
        return {"ok": True, "total_rows": int(total), "max_rows": MAX_ROWS}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def ensure_indexes() -> None:
    """Idempotent index creation (called from lifespan)."""
    try:
        await core_db[COLLECTION].create_index([("ts", -1)])
        await core_db[COLLECTION].create_index([("name", 1), ("ts", -1)])
    except Exception as e:  # noqa: BLE001
        print(f"[feature_flags_audit] index error: {type(e).__name__}: {e}", flush=True)
