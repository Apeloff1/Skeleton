"""Direct clean-DB migration and SQLite schema compatibility checks."""
import sqlite3

from skeleton.ai.webcrawler.migrations import SCHEMA_VERSION, migrate
from skeleton.ai.webcrawler.storage import SqliteCrawlStore


def test_migrate_clean_database_without_store_constructor():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    assert migrate(db) == SCHEMA_VERSION
    assert migrate(db) == SCHEMA_VERSION
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"documents", "urls", "checkpoints", "temporal_fragments",
            "evidence_revisions", "source_quality", "action_economics",
            "calibration_outcomes", "ingestion_receipts",
            "durable_frontier"} <= tables
    assert db.execute("SELECT version FROM schema_version").fetchone() == (SCHEMA_VERSION,)
    db.execute("""INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?)""", (
        "0"*64, "https://example.org/", "https://example.org/", "study", "text",
        "text/plain", 100.0, 1.0, "{}", "[]",
    ))
    db.execute("INSERT INTO urls VALUES(?,?)", ("https://example.org/", "0"*64))
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_store_constructor_and_direct_migrations_produce_identical_schema(tmp_path):
    standalone = sqlite3.connect(":memory:")
    migrate(standalone)
    a = {(r[0], r[1], r[2]) for r in standalone.execute(
        "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    )}
    store = SqliteCrawlStore(tmp_path / "crawler.sqlite")
    try:
        b = {(r[0], r[1], r[2]) for r in store.db.execute(
            "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )}
        assert a == b
        assert migrate(store.db) == SCHEMA_VERSION
    finally:
        store.close()
