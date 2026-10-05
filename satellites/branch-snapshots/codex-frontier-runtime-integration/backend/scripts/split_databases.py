#!/usr/bin/env python3
"""
split_databases.py — Move heavy content collections from the core DB to the
new content DB (and swarm collections to swarm DB) so that Emergent's
[MONGODB_MIGRATE] step only has to copy the small core DB.

Idempotent. Safe to run multiple times. Destructive for the source (core) DB
but the data already exists in content_db after being moved.

USAGE
-----
  /root/.venv/bin/python /app/backend/scripts/split_databases.py           # apply
  /root/.venv/bin/python /app/backend/scripts/split_databases.py --dry-run # report only

STRATEGY
--------
For each collection in the core DB that is logically a CONTENT collection
(see core/databases.py COLLECTION_MAP):
  • If the dest (content_db.<col>) is already non-empty → drop from core.
  • Else if core has data → aggregate+$out into content_db, then drop from core.

Collections matched by CONTENT_COLLECTIONS (exact) or CONTENT_PREFIXES go to
content_db. SWARM_COLLECTIONS / SWARM_PREFIXES go to swarm_db.
"""
from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

# Ensure we can import sibling core/ package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.databases import (  # noqa: E402
    CORE_DB_NAME,
    CONTENT_DB_NAME,
    SWARM_DB_NAME,
    CONTENT_COLLECTIONS,
    CONTENT_PREFIXES,
    SWARM_COLLECTIONS,
    SWARM_PREFIXES,
    which_db,
)


def classify(name: str) -> str:
    """Return 'content', 'swarm', or 'core'."""
    if name in CONTENT_COLLECTIONS or name.startswith(CONTENT_PREFIXES):
        return "content"
    if name in SWARM_COLLECTIONS or name.startswith(SWARM_PREFIXES):
        return "swarm"
    return "core"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)

    core = client[CORE_DB_NAME]
    content = client[CONTENT_DB_NAME]
    swarm = client[SWARM_DB_NAME]

    print(f"MongoDB URL:  {mongo_url}")
    print(f"Core DB:      {CORE_DB_NAME}")
    print(f"Content DB:   {CONTENT_DB_NAME}")
    print(f"Swarm DB:     {SWARM_DB_NAME}")
    print(f"Mode:         {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print("-" * 72)

    def _stats(d):
        s = d.command("dbStats")
        return s["dataSize"] / 1024 / 1024, s["objects"], s["collections"]

    before_core = _stats(core)
    before_content = _stats(content)
    print(
        f"BEFORE  core={before_core[0]:8.1f} MB / {before_core[1]:>8,} docs  |  "
        f"content={before_content[0]:8.1f} MB / {before_content[1]:>8,} docs"
    )
    print("-" * 72)

    core_names = sorted(core.list_collection_names())
    to_move: list[tuple[str, str]] = []   # (name, dest)
    for n in core_names:
        cls = classify(n)
        if cls == "content":
            to_move.append((n, "content"))
        elif cls == "swarm":
            to_move.append((n, "swarm"))

    if not to_move:
        print("Nothing to move. core DB already clean of content/swarm collections.")
        return 0

    print(f"MOVING {len(to_move)} collection(s) from core → content/swarm:")
    moved, skipped, errors = 0, 0, 0
    for name, dest in to_move:
        dest_db = content if dest == "content" else swarm
        try:
            src_cnt = core[name].estimated_document_count()
            dst_cnt = dest_db[name].estimated_document_count()
        except Exception as e:
            print(f"  [err] count {name}: {e}")
            errors += 1
            continue

        if src_cnt == 0:
            # Nothing to move; just drop empty source
            if args.dry_run:
                print(f"  DROP (empty): {name:<40s} → {dest}_db")
            else:
                core[name].drop()
            skipped += 1
            continue

        if dst_cnt >= src_cnt:
            # Dest already has >= data; core is stale/duplicate. Just drop core.
            if args.dry_run:
                print(f"  DROP (dest ≥ src): {name:<40s} src={src_cnt:,} dst={dst_cnt:,}")
            else:
                core[name].drop()
            skipped += 1
            continue

        # Dest is empty or smaller → move via $out (creates dest collection on dest DB)
        if args.dry_run:
            print(f"  MOVE: {name:<40s} src={src_cnt:,} dst={dst_cnt:,} → {dest}_db")
            continue

        try:
            # MongoDB $out with db: ... writes to different database. Requires
            # the aggregation to run on the source collection.
            core[name].aggregate(
                [{"$out": {"db": dest_db.name, "coll": name}}],
                allowDiskUse=True,
            )
            core[name].drop()
            moved += 1
            if args.verbose:
                print(f"  ✓ moved {name} ({src_cnt:,} docs → {dest}_db)")
        except Exception as e:
            errors += 1
            print(f"  [err] move {name}: {e}")

    # Compact core db to reclaim space (best-effort)
    if not args.dry_run:
        try:
            core.command({"compact": "_placeholder_"})
        except Exception:
            pass

    after_core = _stats(core)
    after_content = _stats(content)
    print("-" * 72)
    print(f"MOVED={moved}  SKIPPED={skipped}  ERRORS={errors}")
    print(
        f"AFTER   core={after_core[0]:8.1f} MB / {after_core[1]:>8,} docs  |  "
        f"content={after_content[0]:8.1f} MB / {after_content[1]:>8,} docs"
    )
    print(
        f"DELTA   core={before_core[0]-after_core[0]:+8.1f} MB / {before_core[1]-after_core[1]:+,} docs"
    )
    if not args.dry_run:
        print("\n✓ Split complete. Core DB is now MIGRATE-ready.")
        print("  Content/swarm DBs are skipped by MONGODB_MIGRATE and rebuilt on prod boot from seeds.")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
