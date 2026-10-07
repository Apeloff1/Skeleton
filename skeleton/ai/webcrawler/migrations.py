"""Explicit durable crawler schema migrations."""
from __future__ import annotations
SCHEMA_VERSION=5
MIGRATIONS={
 1:(),
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
}
def migrate(db):
 db.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)")
 row=db.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
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
