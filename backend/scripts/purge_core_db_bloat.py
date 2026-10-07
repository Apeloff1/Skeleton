#!/usr/bin/env python3
"""One-shot purge: remove collections from test_database (core_db) that
should live in content_db / swarm_db per core/databases.py routing.

This eliminates the 521MB → Atlas migration that's silently failing the
K8s deploy's MONGODB_MIGRATE phase. After running, core_db will be lean
(< 50MB) and migrate will complete in seconds.

Run with: python /app/backend/scripts/purge_core_db_bloat.py [--dry-run]
"""
import sys
sys.path.insert(0, '/app/backend')

from pymongo import MongoClient
import os
from core.databases import (
    CONTENT_COLLECTIONS,
    CONTENT_PREFIXES,
    SWARM_COLLECTIONS,
    SWARM_PREFIXES,
    CORE_DB_NAME,
)

DRY_RUN = "--dry-run" in sys.argv

def should_purge(name: str) -> str | None:
    if name in CONTENT_COLLECTIONS:
        return "content (exact)"
    if name.startswith(CONTENT_PREFIXES):
        return f"content (prefix {next(p for p in CONTENT_PREFIXES if name.startswith(p))})"
    if name in SWARM_COLLECTIONS:
        return "swarm (exact)"
    if name.startswith(SWARM_PREFIXES):
        return f"swarm (prefix {next(p for p in SWARM_PREFIXES if name.startswith(p))})"
    return None


def main():
    client = MongoClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
        serverSelectionTimeoutMS=5000,
    )
    db = client[CORE_DB_NAME]

    total_size_before = db.command("dbStats")["dataSize"]
    print(f"core_db ({CORE_DB_NAME}) starting size: {total_size_before/1024/1024:.1f} MB")

    purged = []
    kept = []
    for name in db.list_collection_names():
        if name.startswith("system."):
            continue
        reason = should_purge(name)
        if reason:
            try:
                stats = db.command("collStats", name)
                purged.append((name, stats["size"], stats["count"], reason))
            except Exception:
                purged.append((name, 0, 0, reason))
        else:
            kept.append(name)

    print(f"\nWill PURGE {len(purged)} routable collections, KEEP {len(kept)} user/core collections")
    print(f"{'─'*78}")
    total_purge_size = sum(s for _, s, _, _ in purged)
    print(f"Bytes to purge: {total_purge_size/1024/1024:.1f} MB ({sum(c for _, _, c, _ in purged):,} docs)")

    if not purged:
        print("\nNothing to purge. ✓")
        return

    if DRY_RUN:
        print("\n--dry-run set, not actually dropping collections.")
        print("Top 20 collections that would be dropped:")
        purged.sort(key=lambda x: x[1], reverse=True)
        for name, sz, cnt, why in purged[:20]:
            print(f"  {sz/1024/1024:>7.2f} MB ({cnt:>6} docs)  {name:<40}  [{why}]")
        return

    # Actually drop
    purged.sort(key=lambda x: x[1], reverse=True)
    print("\nDropping (largest first):")
    for name, sz, cnt, why in purged:
        try:
            db.drop_collection(name)
            print(f"  ✓ {sz/1024/1024:>6.2f} MB  {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")

    total_size_after = db.command("dbStats")["dataSize"]
    print(f"\ncore_db final size: {total_size_after/1024/1024:.1f} MB")
    print(f"Freed: {(total_size_before - total_size_after)/1024/1024:.1f} MB ({(1 - total_size_after/total_size_before)*100:.1f}% reduction)")
    print(f"Collections kept ({len(kept)}): {', '.join(sorted(kept)[:10])}{'...' if len(kept) > 10 else ''}")


if __name__ == "__main__":
    main()
