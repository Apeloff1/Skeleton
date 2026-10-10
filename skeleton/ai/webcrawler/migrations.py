"""Explicit durable crawler schema migrations."""
from __future__ import annotations
SCHEMA_VERSION=7
MIGRATIONS={
 1:(
  "CREATE TABLE IF NOT EXISTS documents(content_hash TEXT PRIMARY KEY, canonical_url TEXT NOT NULL, fetched_url TEXT NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL, content_type TEXT NOT NULL, fetched_at REAL NOT NULL, source_score REAL NOT NULL, provenance TEXT NOT NULL, links TEXT NOT NULL)",
  "CREATE TABLE IF NOT EXISTS urls(canonical_url TEXT PRIMARY KEY, content_hash TEXT NOT NULL REFERENCES documents(content_hash))",
  "CREATE TABLE IF NOT EXISTS checkpoints(key TEXT PRIMARY KEY, state TEXT NOT NULL)",
 ),
 2:(
  "CREATE TABLE IF NOT EXISTS crawl_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
  "CREATE INDEX IF NOT EXISTS idx_documents_fetched_at ON documents(fetched_at)",
  "CREATE INDEX IF NOT EXISTS idx_urls_content_hash ON urls(content_hash)",
 ),
 3:(
  "CREATE TABLE IF NOT EXISTS durable_frontier(url TEXT PRIMARY KEY, ready_at REAL NOT NULL, priority REAL NOT NULL, depth INTEGER NOT NULL, parent_url TEXT, attempts INTEGER NOT NULL, owner TEXT, lease_token TEXT, lease_expires REAL)",
  "CREATE INDEX IF NOT EXISTS idx_frontier_ready ON durable_frontier(ready_at,priority,url)",
 ),
 4:(
  "CREATE TABLE IF NOT EXISTS ingestion_receipts(ingestion_key TEXT PRIMARY KEY, state TEXT NOT NULL, owner TEXT, token TEXT, lease_expires REAL, receipt TEXT)",
  "CREATE INDEX IF NOT EXISTS idx_ingestion_lease ON ingestion_receipts(state,lease_expires)",
 ),
 5:(
  "CREATE TABLE IF NOT EXISTS ingestion_outbox(operation_id TEXT PRIMARY KEY, ingestion_key TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', result TEXT)",
  "CREATE UNIQUE INDEX IF NOT EXISTS idx_outbox_ingestion_ordinal ON ingestion_outbox(ingestion_key,ordinal)",
  "CREATE INDEX IF NOT EXISTS idx_outbox_pending ON ingestion_outbox(ingestion_key,state,ordinal)",
 ),
 6:(
  "CREATE TABLE IF NOT EXISTS temporal_fragments(fragment_id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
  "CREATE TABLE IF NOT EXISTS evidence_revisions(revision_id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
  "CREATE TABLE IF NOT EXISTS source_quality(source TEXT PRIMARY KEY, alpha REAL NOT NULL, beta REAL NOT NULL)",
 ),
 7:(
  "CREATE TABLE IF NOT EXISTS action_economics(action_type TEXT PRIMARY KEY, attempts INTEGER NOT NULL, successes INTEGER NOT NULL, mean_cost REAL NOT NULL, mean_latency REAL NOT NULL)",
  "CREATE TABLE IF NOT EXISTS calibration_outcomes(outcome_id TEXT PRIMARY KEY, predicted REAL NOT NULL, actual INTEGER NOT NULL, resolved_at REAL NOT NULL, metadata TEXT NOT NULL)",
 ),
}
def migrate(db):
 # Distinguish a new database from one claiming a prior migration. Creating
 # missing tables on an already-versioned DB could conceal destructive loss.
 db.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)")
 row=db.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
 existing={r[0] for r in db.execute(
  "SELECT name FROM sqlite_master WHERE type='table'"
 )}
 base={"documents","urls","checkpoints"}
 if row is not None and not base.issubset(existing):
  raise ValueError("versioned crawler database is missing canonical base tables")
 # Standalone migrate(connection) must initialize the base schema before
 # installing later indexes, just like SqliteCrawlStore does.
 if row is None:
  with db:
   for sql in MIGRATIONS[1]:db.execute(sql)
 version=int(row[0]) if row else 1
 if version>SCHEMA_VERSION:raise ValueError("crawler database schema is newer than runtime")
 for target in range(version+1,SCHEMA_VERSION+1):
  with db:
   for sql in MIGRATIONS[target]:db.execute(sql)
   db.execute("DELETE FROM schema_version");db.execute("INSERT INTO schema_version VALUES(?)",(target,))
 if row is None:
  with db:
   db.execute("DELETE FROM schema_version");db.execute("INSERT INTO schema_version VALUES(?)",(SCHEMA_VERSION,))
 return SCHEMA_VERSION
