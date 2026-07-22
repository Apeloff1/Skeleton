#!/usr/bin/env python3
"""
deploy_prep.py — Verify the dev MongoDB is ready for Emergent's
[MONGODB_MIGRATE] step and optionally run the database split.

BACKGROUND
----------
The app uses THREE databases on the same MongoDB cluster:

  • <DB_NAME>          (core)    — user-facing state. MIGRATED to prod.
  • <DB_NAME>_content  (content) — regenerable seed data. NOT migrated.
  • <DB_NAME>_swarm    (swarm)   — hyperscale scratch.  NOT migrated.

Because the platform MONGODB_MIGRATE step only copies <DB_NAME>, only the
first DB needs to be small. The content+swarm DBs are rebuilt by the seeders
on prod boot and are invisible to MIGRATE.

This script:
  1. Reports sizes of all three databases.
  2. Warns if the core DB has content collections that should be moved.
  3. Offers to run `split_databases.py` automatically.

USAGE
-----
  /root/.venv/bin/python /app/backend/scripts/deploy_prep.py             # report + auto-split if needed
  /root/.venv/bin/python /app/backend/scripts/deploy_prep.py --dry-run   # report only
  /root/.venv/bin/python /app/backend/scripts/deploy_prep.py --force     # split even if core looks clean

WORKFLOW
--------
  1. $ python deploy_prep.py        ← confirms core DB is small
  2. Click "Deploy" on Emergent.    ← MIGRATE flies through
  3. Prod boots, seeders populate content_db + swarm_db.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from core.databases import (  # noqa: E402
    CORE_DB_NAME,
    CONTENT_DB_NAME,
    SWARM_DB_NAME,
    CONTENT_COLLECTIONS,
    CONTENT_PREFIXES,
    SWARM_COLLECTIONS,
    SWARM_PREFIXES,
)

# Core DB should stay under this size to keep MIGRATE fast & reliable.
MIGRATE_BUDGET_MB = 100


def classify(name: str) -> str:
    if name in CONTENT_COLLECTIONS or name.startswith(CONTENT_PREFIXES):
        return "content"
    if name in SWARM_COLLECTIONS or name.startswith(SWARM_PREFIXES):
        return "swarm"
    return "core"


def db_summary(client: MongoClient, name: str) -> dict:
    d = client[name]
    s = d.command("dbStats")
    return {
        "name": name,
        "size_mb": s["dataSize"] / 1024 / 1024,
        "docs": s["objects"],
        "cols": s["collections"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, don't split")
    parser.add_argument("--force", action="store_true", help="run split even if core looks clean")
    parser.add_argument("--no-split", action="store_true", help="never run split, just report")
    args = parser.parse_args()

    load_dotenv(BACKEND_ROOT / ".env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)

    core = db_summary(client, CORE_DB_NAME)
    content = db_summary(client, CONTENT_DB_NAME)
    swarm = db_summary(client, SWARM_DB_NAME)

    print(f"MongoDB:        {mongo_url}")
    print(f"Migrate budget: <= {MIGRATE_BUDGET_MB} MB for core DB")
    print("-" * 72)
    print(f"  {'DB':<30s} {'SIZE':>10s}   {'DOCS':>10s}   {'COLS':>5s}   ROLE")
    print(f"  {core['name']:<30s} {core['size_mb']:>7.1f} MB  {core['docs']:>10,}   {core['cols']:>5}   MIGRATED to prod")
    print(f"  {content['name']:<30s} {content['size_mb']:>7.1f} MB  {content['docs']:>10,}   {content['cols']:>5}   skipped (rebuilt on boot)")
    print(f"  {swarm['name']:<30s} {swarm['size_mb']:>7.1f} MB  {swarm['docs']:>10,}   {swarm['cols']:>5}   skipped (rebuilt on boot)")
    print("-" * 72)

    # Check for content collections lingering in the core DB
    core_db_h = client[CORE_DB_NAME]
    stray_content = []
    stray_swarm = []
    for n in core_db_h.list_collection_names():
        cls = classify(n)
        if cls == "content":
            try:
                cnt = core_db_h[n].estimated_document_count()
            except Exception:
                cnt = 0
            stray_content.append((n, cnt))
        elif cls == "swarm":
            try:
                cnt = core_db_h[n].estimated_document_count()
            except Exception:
                cnt = 0
            stray_swarm.append((n, cnt))

    needs_split = bool(stray_content or stray_swarm) or core["size_mb"] > MIGRATE_BUDGET_MB

    if stray_content:
        print(f"\n⚠ {len(stray_content)} content collection(s) in core DB (should be moved):")
        for n, c in sorted(stray_content, key=lambda x: -x[1])[:10]:
            print(f"    {n:<40s} {c:>8,} docs")
        if len(stray_content) > 10:
            print(f"    ... and {len(stray_content) - 10} more")
    if stray_swarm:
        print(f"\n⚠ {len(stray_swarm)} swarm collection(s) in core DB (should be moved):")
        for n, c in sorted(stray_swarm, key=lambda x: -x[1])[:10]:
            print(f"    {n:<40s} {c:>8,} docs")

    # Verdict
    print()
    if core["size_mb"] <= MIGRATE_BUDGET_MB and not stray_content and not stray_swarm and not args.force:
        print("✓ Core DB is MIGRATE-ready. Click 'Deploy' on Emergent now.")
        print("  Prod will rebuild content/swarm DBs from seeds on first boot.")
        return 0

    if args.dry_run:
        print("[dry-run] Core DB would benefit from a split. Re-run without --dry-run to apply.")
        return 1 if needs_split else 0

    if args.no_split:
        print("⚠ Core DB is above budget but --no-split was set. Deploy at your own risk.")
        return 1

    # Auto-run split
    print("→ Running split_databases.py to shrink core DB…")
    split = BACKEND_ROOT / "scripts" / "split_databases.py"
    rc = subprocess.call([sys.executable, str(split)])
    if rc != 0:
        print("✗ split failed; check output above.")
        return rc

    # Re-report
    core2 = db_summary(client, CORE_DB_NAME)
    print("-" * 72)
    print(f"After split:  core={core2['size_mb']:.1f} MB / {core2['docs']:,} docs / {core2['cols']} cols")
    if core2["size_mb"] <= MIGRATE_BUDGET_MB:
        print("✓ Core DB is now MIGRATE-ready. Click 'Deploy'.")
        return 0
    print(f"⚠ Core DB is still above {MIGRATE_BUDGET_MB} MB budget. Manual review needed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
