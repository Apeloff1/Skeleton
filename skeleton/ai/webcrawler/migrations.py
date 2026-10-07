"""Explicit durable crawler schema migrations."""
from __future__ import annotations
SCHEMA_VERSION=2
MIGRATIONS={
 1:(),
 2:(
  "CREATE TABLE IF NOT EXISTS crawl_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
  "CREATE INDEX IF NOT EXISTS idx_documents_fetched_at ON documents(fetched_at)",
  "CREATE INDEX IF NOT EXISTS idx_urls_content_hash ON urls(content_hash)",
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
