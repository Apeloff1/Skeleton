"""Transactional, bounded cooperative archive of exact frontier campaign orders.

SQLite is the committed authority. Independently pinned chain heads bind
the caller's expected history. The database is not an authenticated vault
or a proof of physical device/crash recovery. No source file is overwritten.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

from skeleton.app.frontier_campaign_source import build_campaign,identity,sha
from skeleton.app.frontier_campaign_history import (
    GENESIS,MAX_VERSIONS,MAX_REPLAY_STEPS,MAX_STORED_BYTES,event_body,project,
)
from skeleton.app.recovered_evidence import EvidenceError, canonical, digest, pin, seal

_SCHEMA="""
CREATE TABLE IF NOT EXISTS frontier_archive_events_v1 (
    scope TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence>=0),
    previous TEXT NOT NULL,
    head TEXT NOT NULL,
    manifest TEXT NOT NULL,
    source BLOB NOT NULL,
    steps INTEGER NOT NULL CHECK(steps>0),
    PRIMARY KEY(scope,sequence),
    UNIQUE(scope,manifest)
);
"""
MAX_DB_BYTES=256*1024*1024


def _open(path,*,write):
    p=Path(path)
    if p.is_symlink() or (p.exists() and not p.is_file()):
        raise EvidenceError("cooperative archive path must be a regular file")
    if not write and not p.is_file():
        raise EvidenceError("archive not initialized")
    if p.exists() and p.stat().st_size>MAX_DB_BYTES:
        raise EvidenceError("archive file size ceiling")
    conn=sqlite3.connect(str(p) if write else p.resolve().as_uri()+"?mode=ro",
                         uri=not write,isolation_level=None,timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        if write:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            page_size=conn.execute("PRAGMA page_size").fetchone()[0]
            conn.execute(f"PRAGMA max_page_count={MAX_DB_BYTES//page_size}")
            conn.executescript(_SCHEMA)
        else:
            conn.execute("PRAGMA query_only=ON")
        return conn
    except BaseException:
        conn.close()
        raise


def _rows(conn,scope):
    # Check durable size before bringing source BLOBs into process memory.
    count,size,steps=conn.execute(
        "SELECT COUNT(*),COALESCE(SUM(length(source)),0),COALESCE(SUM(steps),0) "
        "FROM frontier_archive_events_v1 WHERE scope=?",(scope,)).fetchone()
    if count>MAX_VERSIONS or size>MAX_STORED_BYTES or steps>MAX_REPLAY_STEPS:
        raise EvidenceError("archive scope capacity exceeded")
    return conn.execute(
        "SELECT sequence,previous,head,manifest,source,steps FROM frontier_archive_events_v1 "
        "WHERE scope=? ORDER BY sequence LIMIT ?",(scope,MAX_VERSIONS+1)).fetchall()


def append_campaign(path,scope,order,*,expected_head,authorized):
    if authorized is not True:
        raise PermissionError("explicit archive writer required")
    scope=identity(scope)
    sha(expected_head)
    export,evidence=build_campaign(order)
    source=canonical(order)
    conn=_open(path,write=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows=_rows(conn,scope)
            # Re-execute retained source before granting a new version;
            # a correct-looking last hash alone is not enough.
            project(scope,rows,retention=MAX_VERSIONS,history_limit=MAX_VERSIONS,
                    expected_head=expected_head)
            if (len(rows)>=MAX_VERSIONS or
                sum(len(row[4]) for row in rows)+len(source)>MAX_STORED_BYTES or
                sum(row[5] for row in rows)+evidence["step_count"]>MAX_REPLAY_STEPS):
                raise EvidenceError("archive scope capacity exhausted")
            if any(row[3]==export.manifest for row in rows):
                raise EvidenceError("canonical campaign manifest already archived")
            seq=len(rows)
            event=event_body(scope,seq,expected_head,order,evidence)
            head=digest(event)
            conn.execute("INSERT INTO frontier_archive_events_v1 VALUES(?,?,?,?,?,?,?)",
                         (scope,seq,expected_head,head,export.manifest,source,evidence["step_count"]))
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return seal({"schema":"skeleton.frontier-campaign.archive-append.v1",
                     "event":event,"head":head,"committed":True,"model_inference_executed":False,
                     "release_certified":False})
    finally:
        conn.close()


def audit_archive(path,scope,*,expected_head,retention=32,history_limit=32,campaign_id=None,authorized):
    if authorized is not True:
        raise PermissionError("explicit archive reader required")
    scope=identity(scope)
    sha(expected_head)
    if campaign_id is not None:
        identity(campaign_id)
    conn=_open(path,write=False)
    try:
        conn.execute("BEGIN")
        rows=_rows(conn,scope)
        result=project(scope,rows,retention=retention,history_limit=history_limit,
                       expected_head=expected_head,campaign_id=campaign_id)
        conn.execute("COMMIT")
        return result
    finally:
        conn.close()
