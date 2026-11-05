"""Exact-commit source lineage bound to immutable corpus revision and SHA."""
from __future__ import annotations
from ..contracts import KnowledgeError

VERSION=1
DDL='''CREATE TABLE IF NOT EXISTS ai_kb_git_lineage (
    principal TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    path TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    blob_oid TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    PRIMARY KEY(principal,doc_id,revision),
    FOREIGN KEY(principal,doc_id,revision)
      REFERENCES ai_kb_documents(principal,doc_id,revision)
)'''


def install(db):
    with db.transaction() as conn:
        conn.execute(DDL)
        entry=conn.execute("SELECT value FROM controls WHERE control='ai_kb_git_schema'").fetchone()
        if entry is None:
            count=conn.execute('SELECT COUNT(*) FROM ai_kb_git_lineage').fetchone()[0]
            if count:raise KnowledgeError('unversioned Git evidence requires operator migration')
            conn.execute("INSERT INTO controls VALUES ('ai_kb_git_schema',?)",(str(VERSION),))
        elif entry!=(str(VERSION),):
            raise KnowledgeError('unsupported Git source lineage schema')


def verify(conn):
    version=conn.execute("SELECT value FROM controls WHERE control='ai_kb_git_schema'").fetchone()
    if version!=(str(VERSION),):raise KnowledgeError('Git source registry absent or obsolete')
