"""
╔══════════════════════════════════════════════════════════════════════════╗
║           TUTOLAGE HYPERSCALE DATABASE SEEDER v2.0                      ║
║   Seeds ALL academy tracks, bibles, exercises, assessments to MongoDB   ║
║   Pre-seeded static content — NO AI generation                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import asyncio
import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent.parent / '.env')

logger = logging.getLogger("Tutolage.Seeder")

# Import all data generators
from seeds.academy_data import get_all_tracks, get_all_academies, get_all_bibles
from seeds.bible_data_expanded import get_expanded_bibles
from seeds.gamedev_data import get_gamedev_tracks
from seeds.algo_challenges_data import get_algo_challenges
from seeds.ai_knowledge_vault import get_ai_knowledge_vault
from seeds.vault_languages import get_vault_languages
from seeds.vault_frameworks import get_vault_frameworks
from seeds.vault_ml_data import get_vault_ml_data
from seeds.vault_architecture import get_vault_architecture
from seeds.tracks_expansion import get_expanded_tracks
from seeds.tracks_20k import get_20k_tracks
from seeds.challenges_mega import get_mega_challenges
from seeds.mega_generator import get_mega_tracks as get_gen_tracks, get_mega_bibles as get_gen_bibles, get_mega_challenges as get_gen_challenges, get_mega_vault as get_gen_vault
from seeds.knowledge_databases import (
    get_all_knowledge_databases, get_interactive_quizzes,
    get_hyperscale_bibles, get_computing_history_database,
)
from seeds.hyperscale_expansion import get_all_expanded_databases, get_expanded_quiz_domains
from seeds.reading_library import get_reading_library, get_reading_categories
from seeds.reading_library_mega import get_mega_reading_library
from seeds.study_paths import get_study_paths
from seeds.library_500 import get_500_books, get_supplemental_books
from seeds.bugfix_library import get_bugfix_library
from seeds.bugfix_mega import get_mega_bugfix_library
from seeds.bugfix_complete import get_complete_bugfix_encyclopedia
from seeds.reference_encyclopedia import get_all_reference_data
from seeds.achievements_mega import get_mega_achievements


async def seed_database(db):
    """Master seeder — idempotent, runs on every startup if collections empty."""
    # Flagged heavy module (~4MB) — imported lazily here so it stays OFF the
    # import-time / cold-start path and only loads when the seeder actually runs.
    from seeds.rosetta_curriculum import (
        ROSETTA_TRACKS, ROSETTA_SUBJECTS, ROSETTA_QUIZZES, ROSETTA_KNOWLEDGE)
    logger.info("═" * 60)
    logger.info("TUTOLAGE HYPERSCALE SEEDER — Checking database state...")
    logger.info("═" * 60)

    existing_tracks = await db.academy_tracks.count_documents({})
    existing_bibles = await db.bible_entries.count_documents({})
    existing_subjects = await db.academy_subjects.count_documents({})
    existing_exercises = await db.exercises.count_documents({})
    existing_challenges = await db.algo_challenges.count_documents({})

    total_existing = existing_tracks + existing_bibles + existing_subjects + existing_exercises + existing_challenges

    

    

    if total_existing > 50:
        logger.info(f"Database already seeded ({total_existing} docs). Skipping.")
        return {"status": "already_seeded", "total_documents": total_existing}

    # DROP EVERYTHING

#     await db.academy_tracks.drop()
#     await db.academy_subjects.drop()
#     await db.bible_entries.drop()
#     await db.exercises.drop()
#     await db.assessments.drop()
#     await db.projects.drop()
#     await db.algo_challenges.drop()
#     await db.knowledge_vault.drop()
#     await db.knowledge_databases.drop()
#     await db.interactive_quizzes.drop()
#     await db.reading_library.drop()
#     await db.study_paths.drop()
#     await db.bugfix_library.drop()
#     await db.achievements_catalog.drop()

    logger.info("Seeding fresh database — HYPERSCALE mode...")

    stats = {
        "tracks_inserted": 0,
        "subjects_inserted": 0,
        "bibles_inserted": 0,
        "exercises_inserted": 0,
        "assessments_inserted": 0,
        "projects_inserted": 0,
        "challenges_inserted": 0,
    }

    # ── 1. LANGUAGE TRACKS ───────────────────────────────────────────
    tracks = get_all_tracks()
    gamedev_tracks = get_gamedev_tracks()
    expanded_tracks = get_expanded_tracks()
    tracks_20k = get_20k_tracks()
    all_tracks = tracks + gamedev_tracks + expanded_tracks + tracks_20k + get_gen_tracks()

    # Deduplicate tracks by id (last wins)
    seen_track_ids = set()
    deduped_tracks = []
    for t in reversed(all_tracks):
        if t["id"] not in seen_track_ids:
            seen_track_ids.add(t["id"])
            deduped_tracks.append(t)
    all_tracks = list(reversed(deduped_tracks))

    exercises_batch = []
    assessments_batch = []
    projects_batch = []

    for track in all_tracks:
        track["_type"] = "language_track"
        track["seeded_at"] = datetime.now(timezone.utc).isoformat()
        track["total_lessons"] = 0
        track["total_exercises"] = 0

        for module in track.get("modules", []):
            for lesson in module.get("lessons", []):
                track["total_lessons"] += 1
                if "exercise" in lesson:
                    ex = lesson.pop("exercise")
                    ex["track_id"] = track["id"]
                    ex["module_id"] = module["id"]
                    ex["lesson_id"] = lesson["id"]
                    ex["seeded_at"] = datetime.now(timezone.utc).isoformat()
                    exercises_batch.append(ex)
                    track["total_exercises"] += 1

            if "project" in module:
                proj = module.pop("project")
                proj["track_id"] = track["id"]
                proj["module_id"] = module["id"]
                proj["seeded_at"] = datetime.now(timezone.utc).isoformat()
                projects_batch.append(proj)

            if "assessment" in module:
                assess = module.pop("assessment")
                assess["track_id"] = track["id"]
                assess["module_id"] = module["id"]
                assess["seeded_at"] = datetime.now(timezone.utc).isoformat()
                assessments_batch.append(assess)



    # -- INJECT ROSETTA MEGA CURRICULUM --
    for t in ROSETTA_TRACKS:
        t.pop('_id', None)
        t["seeded_at"] = datetime.now(timezone.utc).isoformat()
        t["id"] = t["id"]
        t["_type"] = "track"
        all_tracks.append(t)

        
    for s in ROSETTA_SUBJECTS:
        s["seeded_at"] = datetime.now(timezone.utc).isoformat()
        s["id"] = s["id"]
        s["_type"] = "subject"
        pass

    

    # Insert Rosetta Subjects
    for s in ROSETTA_SUBJECTS:
        s.pop('_id', None)
        s["seeded_at"] = datetime.now(timezone.utc).isoformat()
        s["id"] = s["id"]
        s["_type"] = "subject"

    await db.academy_subjects.insert_many(ROSETTA_SUBJECTS)
    stats["subjects_inserted"] = len(ROSETTA_SUBJECTS)

    if all_tracks:
        await db.academy_tracks.insert_many(all_tracks)
        stats["tracks_inserted"] = len(all_tracks)
        logger.info(f"  ✓ {len(all_tracks)} language tracks inserted")

    if exercises_batch:
        await db.exercises.insert_many(exercises_batch)
        stats["exercises_inserted"] = len(exercises_batch)
        logger.info(f"  ✓ {len(exercises_batch)} exercises inserted")

    if assessments_batch:
        await db.assessments.insert_many(assessments_batch)
        stats["assessments_inserted"] = len(assessments_batch)
        logger.info(f"  ✓ {len(assessments_batch)} assessments inserted")

    if projects_batch:
        await db.projects.insert_many(projects_batch)
        stats["projects_inserted"] = len(projects_batch)
        logger.info(f"  ✓ {len(projects_batch)} projects inserted")

    # ── 2. SUBJECT ACADEMIES ─────────────────────────────────────────
    academies = get_all_academies()
    for acad in academies:
        acad["_type"] = "subject_academy"
        acad["seeded_at"] = datetime.now(timezone.utc).isoformat()

    if academies:
        await db.academy_subjects.insert_many(academies)
        stats["subjects_inserted"] = len(academies)
        logger.info(f"  ✓ {len(academies)} subject academies inserted")

    # ── 3. KNOWLEDGE BIBLES ──────────────────────────────────────────
    bibles = get_all_bibles()
    expanded = get_expanded_bibles()
    from seeds.bibles_mega import get_mega_bibles
    mega_bibles = get_mega_bibles()
    gen_bibles = get_gen_bibles()
    all_bibles = bibles + expanded + mega_bibles + gen_bibles
    # Dedup bibles
    seen_b = set()
    deduped_b = []
    for b in all_bibles:
        if b["id"] not in seen_b:
            seen_b.add(b["id"])
            deduped_b.append(b)
    all_bibles = deduped_b
    for bible in all_bibles:
        bible["_type"] = "knowledge_bible"
        bible["seeded_at"] = datetime.now(timezone.utc).isoformat()

    if all_bibles:
        await db.bible_entries.insert_many(all_bibles)
        stats["bibles_inserted"] = len(all_bibles)
        logger.info(f"  ✓ {len(all_bibles)} knowledge bibles inserted")

    # ── 3b. GAME DATABASE ────────────────────────────────────────────
    from seeds.game_database import get_game_database
    game_db = get_game_database()
    game_docs = []
    for key, items in game_db.items():
        for item in items:
            item["_type"] = f"game_{key}"
            item["seeded_at"] = datetime.now(timezone.utc).isoformat()
            game_docs.append(item)
    if game_docs:
        await db.game_database.insert_many(game_docs)
        stats["game_db_inserted"] = len(game_docs)
        logger.info(f"  ✓ {len(game_docs)} game database entries inserted")

    # ── 3c. MATH DATABASE ────────────────────────────────────────────
    from seeds.math_database import get_math_database
    math_db = get_math_database()
    math_docs = []
    for key, items in math_db.items():
        for item in items:
            item["_type"] = f"math_{key}"
            item["seeded_at"] = datetime.now(timezone.utc).isoformat()
            math_docs.append(item)
    if math_docs:
        await db.math_database.insert_many(math_docs)
        stats["math_db_inserted"] = len(math_docs)
        logger.info(f"  ✓ {len(math_docs)} math database entries inserted")

    # ── 4. ALGORITHM CHALLENGES ──────────────────────────────────────
    challenges = get_algo_challenges()
    mega_ch = get_mega_challenges()
    gen_ch = get_gen_challenges()
    all_challenges = challenges + mega_ch + gen_ch
    # Dedup challenges
    seen_ch = set()
    deduped_ch = []
    for ch in all_challenges:
        if ch["id"] not in seen_ch:
            seen_ch.add(ch["id"])
            deduped_ch.append(ch)
    all_challenges = deduped_ch
    for ch in all_challenges:
        ch["seeded_at"] = datetime.now(timezone.utc).isoformat()
    if all_challenges:
        await db.algo_challenges.insert_many(all_challenges)
        stats["challenges_inserted"] = len(all_challenges)
        logger.info(f"  ✓ {len(all_challenges)} algorithm challenges inserted")

    # ── 5. AI KNOWLEDGE VAULT ────────────────────────────────────────
    vault_entries = get_ai_knowledge_vault()
    vault_entries += get_vault_languages()
    vault_entries += get_vault_frameworks()
    vault_entries += get_vault_ml_data()
    vault_entries += get_vault_architecture()
    # Deduplicate by id
    from seeds.vault_final import get_vault_final
    vault_entries += get_vault_final()
    from seeds.vault_mega import get_vault_mega
    vault_entries += get_vault_mega()
    gen_vault = get_gen_vault()
    vault_entries += gen_vault
    seen_ids = set()
    deduped = []
    for entry in vault_entries:
        if entry["id"] not in seen_ids:
            seen_ids.add(entry["id"])
            deduped.append(entry)
    vault_entries = deduped
    for entry in vault_entries:
        entry["seeded_at"] = datetime.now(timezone.utc).isoformat()
    if vault_entries:
        await db.knowledge_vault.insert_many(vault_entries)
        stats["vault_inserted"] = len(vault_entries)
        logger.info(f"  ✓ {len(vault_entries)} knowledge vault entries inserted")

    # ── 6. KNOWLEDGE DATABASES (CS, Physics, Rendering, Architecture, History) ──
    knowledge_dbs = get_all_knowledge_databases()
    kb_docs = []
    for domain_key, domain_data in knowledge_dbs.items():
        for list_key, items in domain_data.items():
            for item in items:
                item["_domain"] = domain_key
                item["_type"] = list_key
                item["seeded_at"] = datetime.now(timezone.utc).isoformat()
                kb_docs.append(item)
    if kb_docs:
        await db.knowledge_databases.insert_many(kb_docs)
        stats["knowledge_dbs_inserted"] = len(kb_docs)
        logger.info(f"  ✓ {len(kb_docs)} knowledge database entries inserted (CS/Physics/Rendering/Architecture/History)")

    # ── 7. HYPERSCALE BIBLES ──────────────────────────────────────────
    hyper_bibles = get_hyperscale_bibles()
    for bible in hyper_bibles:
        bible["_type"] = "knowledge_bible"
        bible["seeded_at"] = datetime.now(timezone.utc).isoformat()
    if hyper_bibles:
        await db.bible_entries.insert_many(hyper_bibles)
        stats["bibles_inserted"] = stats.get("bibles_inserted", 0) + len(hyper_bibles)
        logger.info(f"  ✓ {len(hyper_bibles)} hyperscale bibles inserted")

    # ── 8. 10,000 INTERACTIVE QUIZZES ─────────────────────────────────
    logger.info("  Generating 10,000 interactive quizzes...")
    quizzes = get_interactive_quizzes()
    # Insert in batches of 2000 to avoid OOM
    batch_size = 2000
    total_quizzes = 0
    for batch_start in range(0, len(quizzes), batch_size):
        batch = quizzes[batch_start:batch_start + batch_size]
        for q in batch:
            q["seeded_at"] = datetime.now(timezone.utc).isoformat()
        await db.interactive_quizzes.insert_many(batch)
        total_quizzes += len(batch)
        logger.info(f"    ✓ Quizzes batch inserted: {total_quizzes}/{len(quizzes)}")


    


    seen_rq = set()
    dedup_rq = []
    for q in ROSETTA_QUIZZES:
        if q['id'] not in seen_rq:
            seen_rq.add(q['id'])
            q.pop('_id', None)
            q["seeded_at"] = datetime.now(timezone.utc).isoformat()
            q["_type"] = "quiz"
            dedup_rq.append(q)
    if dedup_rq:
        await db.interactive_quizzes.insert_many(dedup_rq)
        total_quizzes += len(dedup_rq)

    stats["quizzes_inserted"] = total_quizzes
    logger.info(f"  ✓ {total_quizzes} interactive quizzes inserted")

    # ── 9. HYPERSCALE EXPANSION DATABASES ─────────────────────────────
    expanded_dbs = get_all_expanded_databases()
    exp_docs = []
    for domain_key, entries in expanded_dbs.items():
        for item in entries:
            item["_domain"] = domain_key
            item["_type"] = "expanded_field"
            item["seeded_at"] = datetime.now(timezone.utc).isoformat()
            exp_docs.append(item)
    if exp_docs:
        await db.knowledge_databases.insert_many(exp_docs)
        stats["knowledge_dbs_inserted"] = stats.get("knowledge_dbs_inserted", 0) + len(exp_docs)
        logger.info(f"  ✓ {len(exp_docs)} expanded knowledge database entries inserted")

    # ── 10. EXPANDED QUIZZES (5,000 more) ─────────────────────────────
    logger.info("  Generating 5,000 expanded quizzes...")
    exp_quizzes = get_expanded_quiz_domains()
    for batch_start in range(0, len(exp_quizzes), batch_size):
        batch = exp_quizzes[batch_start:batch_start + batch_size]
        for q in batch:
            q["seeded_at"] = datetime.now(timezone.utc).isoformat()
        await db.interactive_quizzes.insert_many(batch)
        total_quizzes += len(batch)


    


    seen_rq = set()
    dedup_rq = []
    for q in ROSETTA_QUIZZES:
        if q['id'] not in seen_rq:
            seen_rq.add(q['id'])
            q.pop('_id', None)
            q["seeded_at"] = datetime.now(timezone.utc).isoformat()
            q["_type"] = "quiz"
            dedup_rq.append(q)
    if dedup_rq:
        await db.interactive_quizzes.insert_many(dedup_rq)
        total_quizzes += len(dedup_rq)

    stats["quizzes_inserted"] = total_quizzes
    logger.info(f"  ✓ {len(exp_quizzes)} expanded quizzes inserted (total: {total_quizzes})")

    # ── 11. READING LIBRARY ───────────────────────────────────────────
    reading_books = get_reading_library()
    mega_books = get_mega_reading_library()
    extra_books = get_500_books()
    supplemental = get_supplemental_books()
    # Dedup by id, mega wins, then extra, then supplemental
    seen_book_ids = set()
    all_books = []
    for book in mega_books + extra_books + supplemental + reading_books:
        if book["id"] not in seen_book_ids:
            seen_book_ids.add(book["id"])
            book["_type"] = "reading_class"
            book["seeded_at"] = datetime.now(timezone.utc).isoformat()
            all_books.append(book)
    if all_books:
        await db.reading_library.insert_many(all_books)
        stats["reading_books_inserted"] = len(all_books)
        logger.info(f"  ✓ {len(all_books)} reading library books/classes inserted")

    # ── 12. STUDY PATHS ──────────────────────────────────────────────
    study_paths = get_study_paths()
    for sp in study_paths:
        sp["_type"] = "study_path"
        sp["seeded_at"] = datetime.now(timezone.utc).isoformat()
    if study_paths:
        await db.study_paths.insert_many(study_paths)
        stats["study_paths_inserted"] = len(study_paths)
        logger.info(f"  ✓ {len(study_paths)} study paths inserted")

    # ── 13. BUG/FIX LIBRARY ──────────────────────────────────────────
    bugfixes = get_bugfix_library()
    mega_bugfixes = get_mega_bugfix_library()
    complete_bugfixes = get_complete_bugfix_encyclopedia()
    # Dedup by id, complete wins, then mega, then original
    seen_ids = set()
    all_bugfixes = []
    for bf in complete_bugfixes + mega_bugfixes + bugfixes:
        if bf["id"] not in seen_ids:
            seen_ids.add(bf["id"])
            bf["seeded_at"] = datetime.now(timezone.utc).isoformat()
            all_bugfixes.append(bf)
    if all_bugfixes:
        await db.bugfix_library.insert_many(all_bugfixes)
        stats["bugfixes_inserted"] = len(all_bugfixes)
        logger.info(f"  ✓ {len(all_bugfixes)} bug/fix entries inserted")

    # ── 14. REFERENCE ENCYCLOPEDIA + WORKAROUND LIBRARY ──────────────
    ref_data = get_all_reference_data()
    for collection_name, docs in ref_data.items():
        if docs:
            for doc in docs:
                doc["seeded_at"] = datetime.now(timezone.utc).isoformat()
            await db[collection_name].insert_many(docs)
            stats[f"{collection_name}_inserted"] = len(docs)
            logger.info(f"  ✓ {len(docs)} {collection_name} entries inserted")

    # ── 15. ACHIEVEMENTS (10,000) ────────────────────────────────────
    logger.info("  Generating achievements...")
    achs = get_mega_achievements()
    batch_size = 2000
    total_achs = 0
    for batch_start in range(0, len(achs), batch_size):
        batch = achs[batch_start:batch_start + batch_size]
        for a in batch:
            a["seeded_at"] = datetime.now(timezone.utc).isoformat()
        await db.achievements_catalog.insert_many(batch)
        total_achs += len(batch)
        logger.info(f"    ✓ Achievements batch: {total_achs}/{len(achs)}")
    stats["achievements_inserted"] = total_achs
    logger.info(f"  ✓ {total_achs} achievements inserted")

    # ── 16. CREATE INDEXES ────────────────────────────────────────────
    await _create_indexes(db)

    total = sum(stats.values())
    logger.info("═" * 60)
    logger.info(f"SEEDING COMPLETE — {total} total documents inserted")
    logger.info(f"  Tracks: {stats['tracks_inserted']} | Subjects: {stats['subjects_inserted']}")
    logger.info(f"  Bibles: {stats['bibles_inserted']} | Exercises: {stats['exercises_inserted']}")
    logger.info(f"  Assessments: {stats['assessments_inserted']} | Projects: {stats['projects_inserted']}")
    logger.info(f"  Challenges: {stats['challenges_inserted']}")
    logger.info(f"  Knowledge DBs: {stats.get('knowledge_dbs_inserted', 0)} | Quizzes: {stats.get('quizzes_inserted', 0)}")
    logger.info(f"  Reading Library: {stats.get('reading_books_inserted', 0)} | Study Paths: {stats.get('study_paths_inserted', 0)}")
    logger.info("═" * 60)

    return {"status": "seeded", "stats": stats, "total": total}


async def _create_indexes(db):
    """Create all indexes for seeded collections."""
    try:
        await db.academy_tracks.create_index("id", unique=True)
        await db.academy_tracks.create_index("category")
        await db.academy_tracks.create_index("total_hours")

        await db.academy_subjects.create_index("id", unique=True)
        await db.academy_subjects.create_index("category")

        await db.bible_entries.create_index("id", unique=True)
        await db.bible_entries.create_index("category")

        await db.exercises.create_index("id", unique=True)
        await db.exercises.create_index("track_id")
        await db.exercises.create_index("module_id")

        await db.assessments.create_index("id", unique=True)
        await db.assessments.create_index("track_id")

        await db.projects.create_index("id", unique=True)
        await db.projects.create_index("track_id")

        await db.algo_challenges.create_index("id", unique=True)
        await db.algo_challenges.create_index("difficulty")
        await db.algo_challenges.create_index("category")

        await db.knowledge_vault.create_index("id", unique=True)
        await db.knowledge_vault.create_index("category")
        await db.knowledge_vault.create_index([("tags", 1)])

        # New collection indexes
        await db.knowledge_databases.create_index("id")
        await db.knowledge_databases.create_index("_domain")
        await db.knowledge_databases.create_index("_type")

        await db.interactive_quizzes.create_index("id", unique=True)
        await db.interactive_quizzes.create_index("domain")
        await db.interactive_quizzes.create_index("topic")
        await db.interactive_quizzes.create_index("difficulty")
        await db.interactive_quizzes.create_index([("domain", 1), ("difficulty", 1)])

        # Reading library indexes
        await db.reading_library.create_index("id", unique=True)
        await db.reading_library.create_index("category")
        await db.reading_library.create_index("difficulty")

        # Study paths indexes
        await db.study_paths.create_index("id", unique=True)
        await db.study_paths.create_index("category")

        # Bugfix library indexes
        await db.bugfix_library.create_index("id", unique=True)
        await db.bugfix_library.create_index("category")
        await db.bugfix_library.create_index("severity")
        await db.bugfix_library.create_index([("tags", 1)])
        await db.bugfix_library.create_index([("searchable", "text")])

        # Progress tracking indexes
        await db.user_progress.create_index([("user_id", 1), ("item_type", 1)])
        await db.user_progress.create_index([("user_id", 1), ("item_id", 1)], unique=True)
        await db.quiz_scores.create_index([("user_id", 1), ("quiz_id", 1)])
        await db.quiz_scores.create_index("total_score")

        logger.info("  ✓ All indexes created")
    except Exception as e:
        logger.warning(f"Index creation partial: {e}")


async def reseed_database(db):
    """Force re-seed: drops all collections and re-creates."""
    logger.info("FORCE RE-SEED — Dropping existing collections...")
    for coll in ["academy_tracks", "academy_subjects", "bible_entries",
                 "exercises", "assessments", "projects", "algo_challenges", "knowledge_vault",
                 "game_database", "math_database", "knowledge_databases", "interactive_quizzes",
                 "reading_library", "study_paths", "bugfix_library",
                 "code_snippets", "cheatsheets", "interview_prep", "flashcard_decks",
                 "career_roadmaps", "project_ideas", "http_status_codes",
                 "complexity_reference", "tech_glossary", "workaround_library",
                 "achievements_catalog"]:
        await db[coll].drop()
    return await seed_database(db)
