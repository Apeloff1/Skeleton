"""Explicit index integrity and reconstitution; corpus rows remain authoritative."""
from __future__ import annotations
import sqlite3
from .contracts import KnowledgeError
from . import events


def verify_index(conn)->dict:
    """FTS5's own external-content integrity check; no persistent change."""
    try:
        # FTS5 verifies postings AND their equality to the external source table.
        # Command is executed inside the caller's transaction. On success it
        # doesn't modify the index; it is not run in read-only doctor paths.
        conn.execute("INSERT INTO ai_kb_fts(ai_kb_fts,rank) VALUES('integrity-check',1)")
        return {'status':'fts5-content-index-verified','rebuilds':0}
    except sqlite3.DatabaseError as exc:
        raise KnowledgeError('FTS5 content or posting list integrity failed') from exc


def rebuild(plane,*,approved:bool=False,maximum:int=65536)->dict:
    if approved is not True:raise KnowledgeError('index rebuild requires explicit independent approval')
    # Never use FTS to invent or revise source rows. Check all source chunks
    # and the full mutation chain *before* generating new posting lists.
    proof=plane.doctor(maximum=maximum)
    with plane.db.transaction() as conn:
        # Prevent rebuilding against a corpus changed after read-only review.
        latest=conn.execute('SELECT event_sha256 FROM ai_kb_events '
            'WHERE principal=? ORDER BY ordinal DESC LIMIT 1',
            (plane.identity.key(),)).fetchone()
        head=latest[0] if latest else '0'*64
        if head!=proof['proof']['event_head_sha256']:
            raise KnowledgeError('source mutation raced operator index rebuild')
        counts=conn.execute('SELECT COUNT(*),COALESCE(SUM(chunks),0) '
            'FROM ai_kb_documents WHERE principal=?',(plane.identity.key(),)).fetchone()
        if counts!=(proof['proof']['revisions'],proof['proof']['chunks']):
            raise KnowledgeError('source inventory changed during index rebuild')
        try:
            conn.execute("INSERT INTO ai_kb_fts(ai_kb_fts) VALUES('rebuild')")
        except sqlite3.DatabaseError as exc:
            raise KnowledgeError('FTS5 rebuild failed') from exc
        verify_index(conn)
        event=events.append(conn,plane.identity.key(),action='index-rebuilt',doc_id='ALL',
                       revision=0,raw_sha256=proof['proof_sha256'],
                       normalized_sha256=proof['proof_sha256'],chunks=proof['proof']['chunks'])
    return {'status':'operator-approved-index-rebuilt','event_sha256':event['event_sha256'],
            'source_custody_sha256':proof['proof_sha256']}
