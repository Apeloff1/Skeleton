"""
═══════════════════════════════════════════════════════════════════════
 Language Classes Auto-Seeder
─────────────────────────────────────────────────────────────────────
 Populates the `language_classes` collection that powers
 /api/languages-academy/* endpoints. Hot-path for the LanguageAcademy
 modal. Pulls from the 500-language curated catalogue.

 Idempotent — re-runs only insert new languages.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

log = logging.getLogger("academy.language_classes_seed")


async def seed_language_classes(db) -> dict:
    """Upsert all 500 languages into `language_classes`. Returns counts."""
    try:
        from seeds.languages_500 import get_500_languages
    except Exception as e:
        log.warning(f"languages_500 import failed: {e}")
        return {"inserted": 0, "skipped": 0, "error": str(e)[:160]}

    langs = get_500_languages()
    if not langs:
        return {"inserted": 0, "skipped": 0, "total": 0}

    # Ensure unique-index on slug & id
    try:
        await db.language_classes.create_index("id", unique=True)
        await db.language_classes.create_index("slug")
        await db.language_classes.create_index("category")
        await db.language_classes.create_index("difficulty")
        await db.language_classes.create_index("executable_in_playground")
    except Exception:
        pass

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0
    BATCH = 200
    for i in range(0, len(langs), BATCH):
        chunk = langs[i:i + BATCH]
        for L in chunk:
            L.setdefault("seeded_at", now)
            try:
                res = await db.language_classes.update_one(
                    {"id": L["id"]}, {"$set": L}, upsert=True,
                )
                if res.upserted_id is not None:
                    inserted += 1
                elif res.modified_count > 0:
                    updated += 1
            except Exception as e:
                log.debug(f"upsert {L.get('id')} failed: {e}")

    total = await db.language_classes.count_documents({})
    log.info(f"[language_classes] seed complete: inserted={inserted} updated={updated} total={total}")
    return {"inserted": inserted, "updated": updated, "total": total}
