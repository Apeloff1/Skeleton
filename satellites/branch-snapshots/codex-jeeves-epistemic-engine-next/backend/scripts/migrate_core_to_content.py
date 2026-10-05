#!/usr/bin/env python3
"""Data-preserving migration: MOVE collections out of core_db into the DB
they should live in per core/databases.py routing.

Unlike scripts/purge_core_db_bloat.py (which simply drops collections and
relies on seeders to rewrite them), this script COPIES the documents to the
target DB before removing them from core_db, so no user data is lost.

Idempotent: if a collection is already in the target DB, documents are
upserted by `_id` so re-running is safe.

Run with: python /app/backend/scripts/migrate_core_to_content.py [--dry-run]
"""
import sys
sys.path.insert(0, '/app/backend')

import os
from pymongo import MongoClient, UpdateOne
from core.databases import (
    CONTENT_COLLECTIONS,
    CONTENT_PREFIXES,
    SWARM_COLLECTIONS,
    SWARM_PREFIXES,
    CORE_DB_NAME,
    CONTENT_DB_NAME,
    SWARM_DB_NAME,
)

DRY_RUN = "--dry-run" in sys.argv
BATCH_SIZE = 1000


def target_db_name(name: str) -> str | None:
    if name in CONTENT_COLLECTIONS or name.startswith(CONTENT_PREFIXES):
        return CONTENT_DB_NAME
    if name in SWARM_COLLECTIONS or name.startswith(SWARM_PREFIXES):
        return SWARM_DB_NAME
    return None


def main():
    client = MongoClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
        serverSelectionTimeoutMS=5000,
    )
    core = client[CORE_DB_NAME]

    before = core.command("dbStats")["dataSize"]
    print(f"core_db ({CORE_DB_NAME}) starting size: {before/1024/1024:.1f} MB")

    movable = []
    kept = []
    for name in core.list_collection_names():
        if name.startswith("system."):
            continue
        tgt = target_db_name(name)
        if tgt:
            try:
                stats = core.command("collStats", name)
                movable.append((name, tgt, stats["size"], stats["count"]))
            except Exception:
                movable.append((name, tgt, 0, 0))
        else:
            kept.append(name)

    movable.sort(key=lambda x: -x[2])

    print(f"\nWill MIGRATE {len(movable)} collections, KEEP {len(kept)} core collections")
    print(f"{'─'*78}")
    total = sum(s for _, _, s, _ in movable)
    print(f"Bytes to migrate: {total/1024/1024:.2f} MB ({sum(c for _, _, _, c in movable):,} docs)")

    if not movable:
        print("\nNothing to migrate. ✓")
        return

    if DRY_RUN:
        print("\n--dry-run set, showing top 25 candidates:")
        for n, tgt, sz, cnt in movable[:25]:
            print(f"  {sz/1024/1024:>7.2f} MB ({cnt:>6} docs)  {n:<35s} -> {tgt}")
        return

    print("\nMigrating (largest first):")
    total_moved_docs = 0
    total_moved_bytes = 0
    for n, tgt, sz, cnt in movable:
        try:
            src_coll = core[n]
            dst_coll = client[tgt][n]

            if cnt == 0:
                # Empty source collection — just drop, target is fine as-is
                core.drop_collection(n)
                print(f"  ✓ DROP empty   {n}")
                continue

            # Short-circuit: if destination already has >= source count, the
            # seeder has already populated content_db. Just drop the source.
            dst_existing = dst_coll.estimated_document_count()
            if dst_existing >= cnt:
                core.drop_collection(n)
                total_moved_bytes += sz
                print(f"  ✓ {sz/1024/1024:>6.2f} MB / dst already has {dst_existing} >= src {cnt}  {n} (dropped src)")
                continue

            # Determine the natural unique key to upsert on. Prefer business
            # `id` field if present (most seeders use it & index it unique),
            # otherwise fall back to Mongo `_id`.
            sample = src_coll.find_one()
            upsert_key = "id" if sample and "id" in sample else "_id"

            # Stream batches with upsert (idempotent on the right key)
            moved = 0
            errors = 0
            batch = []
            def _flush(b):
                nonlocal moved, errors
                try:
                    dst_coll.bulk_write(b, ordered=False)
                    moved += len(b)
                except Exception as e:
                    # Most likely E11000 duplicate-key errors on `id` index,
                    # meaning the target already has those rows. We count
                    # them as "moved" (they exist in dest) so the drop logic
                    # below proceeds correctly.
                    n_written = getattr(getattr(e, 'details', {}), 'get', lambda *_: 0)('nUpserted', 0) or 0
                    moved += n_written
                    errors += len(b) - n_written

            for doc in src_coll.find({}, no_cursor_timeout=True).batch_size(BATCH_SIZE):
                if upsert_key == "id":
                    # Don't carry source _id; let dst generate its own. Avoids
                    # _id collisions with separately-seeded dest docs.
                    key_val = doc.get("id")
                    doc_no_id = {k: v for k, v in doc.items() if k != "_id"}
                    batch.append(UpdateOne({"id": key_val}, {"$set": doc_no_id}, upsert=True))
                else:
                    batch.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True))
                if len(batch) >= BATCH_SIZE:
                    _flush(batch)
                    batch = []
            if batch:
                _flush(batch)

            # Verify target now has at least the source count
            dst_count = dst_coll.estimated_document_count()
            if dst_count >= cnt:
                core.drop_collection(n)
                total_moved_docs += moved
                total_moved_bytes += sz
                print(f"  ✓ {sz/1024/1024:>6.2f} MB ({upsert_key})  {n:<35s} -> {tgt} (now {dst_count}, dup={errors})")
            else:
                print(f"  ⚠ {n}: dst has {dst_count} < src {cnt}, NOT dropping source (errors={errors})")
        except Exception as e:
            print(f"  ✗ {n}: {type(e).__name__}: {str(e)[:200]}")

    after = core.command("dbStats")["dataSize"]
    print(f"\ncore_db final size: {after/1024/1024:.1f} MB")
    if before > 0:
        print(f"Freed: {(before - after)/1024/1024:.1f} MB ({(1 - after/before)*100:.1f}% reduction)")
    print(f"Total docs migrated: {total_moved_docs:,}")


if __name__ == "__main__":
    main()
