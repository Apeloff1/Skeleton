"""Additive, schema-versioned, principal-bound FTS5 projection in SpineDatabase.

The authoritative corpus rows and its FTS5 index live in one SQLite database,
so ingestion revision, chunks, index triggers, audit event and outbox publish
in one transaction. No second durability authority or orphan index build.
"""
from __future__ import annotations
from .contracts import KnowledgeError

VERSION = 1
DDL = (
'''CREATE TABLE IF NOT EXISTS ai_kb_documents (
  principal TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  title TEXT NOT NULL,
  rights TEXT NOT NULL,
  content_type TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL,
  normalized_sha256 TEXT NOT NULL,
  raw_bytes INTEGER NOT NULL CHECK(raw_bytes > 0),
  normalized_bytes INTEGER NOT NULL CHECK(normalized_bytes > 0),
  chunks INTEGER NOT NULL CHECK(chunks >= 0),
  active INTEGER NOT NULL CHECK(active IN (0,1)),
  deleted INTEGER NOT NULL CHECK(deleted IN (0,1)),
  created_ns INTEGER NOT NULL,
  PRIMARY KEY(principal,doc_id,revision),
  FOREIGN KEY(principal) REFERENCES principals(principal)
)''',
'''CREATE UNIQUE INDEX IF NOT EXISTS ai_kb_one_active
    ON ai_kb_documents(principal,doc_id) WHERE active=1''',
'''CREATE INDEX IF NOT EXISTS ai_kb_active_scope
    ON ai_kb_documents(principal,active,doc_id,revision)''',
'''CREATE TABLE IF NOT EXISTS ai_kb_chunks (
  row_id INTEGER PRIMARY KEY,
  principal TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
  char_start INTEGER NOT NULL CHECK(char_start >= 0),
  char_end INTEGER NOT NULL CHECK(char_end > char_start),
  passage TEXT NOT NULL,
  passage_sha256 TEXT NOT NULL,
  document_sha256 TEXT NOT NULL,
  UNIQUE(principal,doc_id,revision,ordinal),
  FOREIGN KEY(principal,doc_id,revision)
    REFERENCES ai_kb_documents(principal,doc_id,revision)
)''',
'''CREATE INDEX IF NOT EXISTS ai_kb_chunks_scope
    ON ai_kb_chunks(principal,doc_id,revision,ordinal)''',
'''CREATE VIRTUAL TABLE IF NOT EXISTS ai_kb_fts USING fts5(
    passage, content='ai_kb_chunks', content_rowid='row_id', tokenize='unicode61')''',
'''CREATE TRIGGER IF NOT EXISTS ai_kb_chunk_ai AFTER INSERT ON ai_kb_chunks BEGIN
    INSERT INTO ai_kb_fts(rowid,passage) VALUES(new.row_id,new.passage);
END''',
'''CREATE TRIGGER IF NOT EXISTS ai_kb_chunk_ad AFTER DELETE ON ai_kb_chunks BEGIN
    INSERT INTO ai_kb_fts(ai_kb_fts,rowid,passage) VALUES('delete',old.row_id,old.passage);
END''',
'''CREATE TRIGGER IF NOT EXISTS ai_kb_chunk_au AFTER UPDATE ON ai_kb_chunks BEGIN
    INSERT INTO ai_kb_fts(ai_kb_fts,rowid,passage) VALUES('delete',old.row_id,old.passage);
    INSERT INTO ai_kb_fts(rowid,passage) VALUES(new.row_id,new.passage);
END''',
'''CREATE TABLE IF NOT EXISTS ai_kb_events (
  principal TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK(ordinal>=1),
  event_json BLOB NOT NULL,
  event_sha256 TEXT NOT NULL,
  previous_sha256 TEXT NOT NULL,
  PRIMARY KEY(principal,ordinal),
  FOREIGN KEY(principal) REFERENCES principals(principal)
)''',
)


def install(db) -> None:
    """Require FTS5 and an exact extension schema marker; no auto migration."""
    try:
        with db.transaction() as conn:
            for command in DDL:
                conn.execute(command)
            row = conn.execute("SELECT value FROM controls WHERE control='ai_knowledge_schema'").fetchone()
            if row is None:
                # No silent adoption of a preexisting undocumented knowledge index.
                prior = conn.execute('SELECT COUNT(*) FROM ai_kb_documents').fetchone()[0]
                if prior:
                    raise KnowledgeError('unversioned knowledge corpus requires migration')
                conn.execute("INSERT INTO controls(control,value) VALUES('ai_knowledge_schema',?)", (str(VERSION),))
            elif row != (str(VERSION),):
                raise KnowledgeError('unsupported knowledge schema version')
            conn.execute("SELECT count(*) FROM ai_kb_fts WHERE ai_kb_fts MATCH ?", ('"known"',)).fetchone()
    except KnowledgeError: raise
    except Exception as exc:
        raise KnowledgeError('FTS5 or knowledge schema unavailable') from exc


def verify(db) -> None:
    """Read-only extension-schema verification for an existing private DB."""
    try:
        with db.snapshot() as conn:
            row = conn.execute("SELECT value FROM controls WHERE control='ai_knowledge_schema'").fetchone()
            if row != (str(VERSION),):
                raise KnowledgeError('knowledge schema uninitialized or unsupported')
            required = {'ai_kb_documents','ai_kb_chunks','ai_kb_fts','ai_kb_events'}
            available = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'ai_kb_%'").fetchall()}
            if not required.issubset(available):
                raise KnowledgeError('incomplete knowledge schema')
    except KnowledgeError:raise
    except Exception as exc:raise KnowledgeError('knowledge schema inspection unavailable') from exc
