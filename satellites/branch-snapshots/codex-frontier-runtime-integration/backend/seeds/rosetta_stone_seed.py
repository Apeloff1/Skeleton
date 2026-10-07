"""
seeds/rosetta_stone_seed.py — Master loader for the Rosetta Stone collection.

Loads:
  • get_ultimo_rosetta(all_languages) — exhaustive concept × language matrix
    (1,517 concepts × 177 languages = ~268,509 entries with handcrafted +
    template-generated code samples)
  • get_true_rosetta()                — handcrafted entries (legacy fallback)
  • get_expanded_v3_rosetta()         — additional v3 handcrafted entries

All entries are inserted into `rosetta_stone` collection (routed to
content_db per core/databases.py CONTENT_COLLECTIONS).

The seeder is idempotent — it spot-checks the collection count and skips if
it's already at target. Inserts in 1000-doc batches with `ordered=False`
so duplicate-id retries don't stall the whole load.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("CodeDock.RosettaStoneSeeder")

# Minimum we'd expect after a successful seed — used to decide whether to
# refill (e.g. after a fresh content_db). Set conservatively low so a
# partial first-run still triggers top-up next boot.
_MIN_ENTRIES = 1000

# How many docs per batch insert_many
_BATCH_SIZE = 1000


def _build_language_list() -> list[dict]:
    """Build the `all_languages` list expected by get_ultimo_rosetta()."""
    try:
        from seeds.rosetta_ultimo import LANG_FAMILY
    except Exception as e:
        logger.warning(f"[rosetta-stone] LANG_FAMILY unavailable: {e}")
        return []
    # Each entry just needs a "name" key
    return [{"name": lang} for lang in sorted(LANG_FAMILY.keys())]


def _gather_all_entries() -> list[dict]:
    """Pull entries from every available rosetta source and dedupe by id."""
    seen: set[str] = set()
    entries: list[dict] = []

    # 1) Ultimo (exhaustive): ~268k entries
    try:
        from seeds.rosetta_ultimo import get_ultimo_rosetta
        langs = _build_language_list()
        if langs:
            ultimo = get_ultimo_rosetta(langs)
            for e in ultimo:
                if e["id"] not in seen:
                    seen.add(e["id"])
                    entries.append(e)
            logger.info(f"[rosetta-stone] +ultimo: {len(ultimo)} entries")
    except Exception as e:
        logger.warning(f"[rosetta-stone] ultimo source failed: {e}")

    # 2) True handcrafted (fallback / extra coverage)
    try:
        from seeds.rosetta_true import get_true_rosetta
        true_entries = get_true_rosetta()
        added = 0
        for e in true_entries:
            if e.get("id") not in seen:
                seen.add(e["id"])
                entries.append(e)
                added += 1
        logger.info(f"[rosetta-stone] +true: {added} new entries (raw {len(true_entries)})")
    except Exception as e:
        logger.warning(f"[rosetta-stone] true source failed: {e}")

    # 3) v3 extras
    try:
        from seeds.rosetta_expanded_v3 import get_expanded_v3_rosetta
        v3 = get_expanded_v3_rosetta()
        added = 0
        for e in v3:
            if e.get("id") not in seen:
                seen.add(e["id"])
                entries.append(e)
                added += 1
        logger.info(f"[rosetta-stone] +v3: {added} new entries (raw {len(v3)})")
    except Exception as e:
        logger.warning(f"[rosetta-stone] v3 source failed: {e}")

    return entries


async def seed_rosetta_stone(db, force: bool = False) -> dict[str, Any]:
    """
    Seed the rosetta_stone collection. Idempotent.

    Args:
        db: Motor AsyncIOMotorDatabase (should be content_db).
        force: If True, drop existing collection and reseed from scratch.

    Returns:
        {'inserted': N, 'total': M, 'languages': K, 'concepts': C}
    """
    coll = db["rosetta_stone"]

    # Spot-check existing
    if not force:
        try:
            existing = await coll.count_documents({}, limit=_MIN_ENTRIES + 1)
            if existing >= _MIN_ENTRIES:
                logger.info(f"[rosetta-stone] already at {existing}+ docs — skipping")
                return {"inserted": 0, "total": existing, "skipped": True}
        except Exception as e:
            logger.warning(f"[rosetta-stone] count check failed: {e}")

    # Build entries
    entries = _gather_all_entries()
    if not entries:
        logger.warning("[rosetta-stone] no entries collected — nothing to seed")
        return {"inserted": 0, "total": 0, "skipped": False, "error": "no sources"}

    logger.info(f"[rosetta-stone] collected {len(entries):,} unique entries — inserting…")

    # Ensure unique index on id so reseeds dedupe cleanly
    try:
        await coll.create_index("id", unique=True)
    except Exception:
        pass

    inserted = 0
    for i in range(0, len(entries), _BATCH_SIZE):
        batch = entries[i : i + _BATCH_SIZE]
        try:
            res = await coll.insert_many(batch, ordered=False)
            inserted += len(res.inserted_ids)
        except Exception as e:
            # BulkWriteError typically — duplicate ids on retry; the
            # successful inserts are still committed.
            msg = str(e)
            if "duplicate key" in msg.lower():
                # Count what landed by querying any one of the IDs
                hit_count = sum(
                    1 for d in batch if await coll.count_documents({"id": d["id"]}, limit=1)
                )
                inserted += hit_count - (len(batch) - hit_count)
            else:
                logger.warning(f"[rosetta-stone] batch {i//_BATCH_SIZE} insert error: {msg[:200]}")

    total = await coll.count_documents({})
    # Build summary
    langs = {e.get("language") for e in entries}
    concepts = {e.get("concept") for e in entries}
    logger.info(
        f"[rosetta-stone] seeded: inserted={inserted:,} total={total:,} "
        f"languages={len(langs)} concepts={len(concepts)}"
    )
    return {
        "inserted": inserted,
        "total": total,
        "languages": len(langs),
        "concepts": len(concepts),
        "skipped": False,
    }
