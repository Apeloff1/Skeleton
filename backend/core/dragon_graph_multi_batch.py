"""Bounded, owner-exclusive concurrent structural reservations.

One root can hold up to four independent owner batches. Distinct owners may
share physical lanes; SQLite serializes writes to the same file. Receipt keys
are sequence-specific. No same-owner parallel reservations or partial public
graph visibility. Root reservation and settlement remain serialized.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import dragon_graph_authority as a
from core.dragon_game_corpus import CatalogueHeld

MAX_PENDING=4
MAX_PENDING_BYTES=64*1024**2
TERMINAL_RETENTION=4096
SCHEMA=(
    """CREATE TABLE structural_multi_identity(singleton INTEGER PRIMARY KEY CHECK(singleton=1),epoch TEXT NOT NULL)""",
    """CREATE TABLE structural_batches(sequence INTEGER PRIMARY KEY,mode TEXT NOT NULL,
      request_sha TEXT,plan TEXT NOT NULL,sha256 TEXT NOT NULL CHECK(length(sha256)=64))""",
    """CREATE TABLE structural_batch_owners(owner TEXT PRIMARY KEY,sequence INTEGER NOT NULL
      REFERENCES structural_batches(sequence) ON DELETE CASCADE) WITHOUT ROWID""",
    """CREATE INDEX structural_batch_owner_seq ON structural_batch_owners(sequence)""",
    """CREATE TABLE structural_terminal(sequence INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('settled','aborted')))""",
)
RECEIPT="""CREATE TABLE structural_receipts(sequence INTEGER PRIMARY KEY,
    plan_sha TEXT NOT NULL CHECK(length(plan_sha)=64),lane_sha TEXT NOT NULL CHECK(length(lane_sha)=64))"""


def enabled(db):
    if not a._table(db,"structural_multi_identity"):
        if any(a._table(db,k) for k in ("structural_batches","structural_batch_owners","structural_terminal")):
            raise a.GraphHeld("incomplete multi-batch identity")
        return False
    from core.dragon_graph_structural import enabled as structural_enabled
    if not structural_enabled(db):raise a.GraphHeld("structural journal missing")
    marker=db.execute("SELECT epoch FROM main.structural_multi_identity WHERE singleton=1").fetchone()
    current=db.execute("SELECT epoch FROM main.dragon_graph_structural WHERE singleton=1").fetchone()
    if not marker or not current or marker[0]!=current[0]:raise a.GraphHeld("multi-batch epoch differs")
    if not all(a._table(db,k) for k in ("structural_batches","structural_batch_owners","structural_terminal")):
        raise a.GraphHeld("multi-batch registry missing")
    return True


def install(root,*,offline_acknowledged=False):
    if offline_acknowledged is not True:raise a.GraphHeld("stop every old writer first")
    from core.dragon_graph_structural import enabled as structural_enabled
    root=Path(root)
    with a._probe_connection(root) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            if not structural_enabled(db):raise a.GraphHeld("enable structural writers first")
            if enabled(db):
                db.execute("COMMIT");return {"installed":True,"replayed":True}
            row=db.execute("SELECT epoch,state,plan FROM main.dragon_graph_structural WHERE singleton=1").fetchone()
            if row["state"]!="idle" or row["plan"]:raise a.GraphHeld("recover legacy pending plan before upgrade")
            for sql in SCHEMA:db.execute(sql)
            db.execute("INSERT INTO main.structural_multi_identity VALUES(1,?)",(row["epoch"],))
            for i in range(a.LANES):
                db.execute(RECEIPT.replace("CREATE TABLE structural_receipts","CREATE TABLE "+a._alias(i)+".structural_receipts",1))
            a._fence(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"installed":True,"replayed":False,"max_pending_batches":MAX_PENDING,"physical_lanes":a.LANES}


def rows(db,sequence=None):
    if sequence is None:
        return db.execute("SELECT sequence,'pending' AS state,plan,sha256,mode,request_sha FROM main.structural_batches ORDER BY sequence LIMIT ?",
                          (MAX_PENDING+1,)).fetchall()
    return db.execute("SELECT sequence,'pending' AS state,plan,sha256,mode,request_sha FROM main.structural_batches WHERE sequence=?",
                      (sequence,)).fetchall()


def owners(db):
    return {r[0] for r in db.execute("SELECT owner FROM main.structural_batch_owners")}


def validate(db,row,plan):
    reserved={r[0] for r in db.execute("SELECT owner FROM main.structural_batch_owners WHERE sequence=?",(row["sequence"],))}
    planned={j["owner"] for j in plan["jobs"]}
    if not reserved or reserved!=planned or row["mode"]!=plan["mode"] or row["request_sha"]!=(plan.get("publication") or {}).get("request_sha"):
        raise a.GraphHeld("multi-batch owner or request witness differs")
    for part in plan["lanes"].values():
        if any(pair[1][0] not in reserved for kind in ("nodes","edges") for pair in part[kind]):
            raise a.GraphHeld("multi-batch row owner differs")
    if any(delta[0] not in reserved for delta in plan["deltas"]) or any(c[0] not in reserved for c in plan["candidates"]) or any(e[0] not in reserved for e in plan["expansions"]) or any(g["owner"] not in reserved for g in plan.get("grants",[])):
        raise a.GraphHeld("multi-batch settlement owner differs")


def fence(db):
    """Publish aggregate visibility hold inside the current root transaction."""
    count=db.execute("SELECT COUNT(*) FROM main.structural_batches").fetchone()[0]
    if count>MAX_PENDING:raise a.GraphHeld("pending batch quota differs")
    db.execute("UPDATE main.dragon_graph_structural SET state=?,plan='',sha256='' WHERE singleton=1",
               ("pending" if count else "idle",))


def assert_fence(db):
    count=db.execute("SELECT COUNT(*) FROM main.structural_batches").fetchone()[0]
    state=db.execute("SELECT state,plan FROM main.dragon_graph_structural WHERE singleton=1").fetchone()
    if count>MAX_PENDING or not state or state[0]!=("pending" if count else "idle") or state[1]:
        raise a.GraphHeld("aggregate multi-batch fence differs")


def unlock_inside_transaction(db):
    # The outer BEGIN IMMEDIATE transaction excludes other root writers.
    # Readers see the previously committed aggregate fence until COMMIT.
    if not db.in_transaction:raise a.GraphHeld("multi-batch transaction required")
    db.execute("UPDATE main.dragon_graph_structural SET state='idle' WHERE singleton=1")


def publish(db,seq,plan,raw,witness):
    existing=owners(db);planned={j["owner"] for j in plan["jobs"]}
    if not planned or planned&existing:raise CatalogueHeld("owner already reserved")
    count,size=db.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(plan AS BLOB))),0) FROM main.structural_batches").fetchone()
    if count>=MAX_PENDING or size+len(raw.encode())>MAX_PENDING_BYTES:
        raise CatalogueHeld("parallel structural journal capacity")
    db.execute("INSERT INTO main.structural_batches VALUES(?,?,?,?,?)",
               (seq,plan["mode"],(plan.get("publication") or {}).get("request_sha"),raw,witness))
    db.executemany("INSERT INTO main.structural_batch_owners VALUES(?,?)",[(owner,seq) for owner in sorted(planned)])
    change=db.execute("UPDATE main.dragon_graph_structural SET sequence=? WHERE singleton=1 AND sequence=?",(seq,seq-1))
    if change.rowcount!=1:raise a.GraphHeld("structural sequence changed")
    fence(db)


def terminal(db,seq,witness):
    row=db.execute("SELECT sha256,state FROM main.structural_terminal WHERE sequence=?",(seq,)).fetchone()
    if row is None or row[0]!=witness:raise a.GraphHeld("structural settlement superseded")
    return {"processed":0,"held":0,"replayed":True,"aborted":row[1]=="aborted","network_executed":False}


def finish(db,plan,witness,*,aborted=False):
    seq=plan["sequence"]
    for key in plan["lanes"]:
        change=db.execute("DELETE FROM "+a._alias(int(key))+".structural_receipts WHERE sequence=?",(seq,))
        if not aborted and change.rowcount!=1:raise a.GraphHeld("settled lane receipt disappeared")
    db.execute("DELETE FROM main.structural_batch_owners WHERE sequence=?",(seq,))
    if db.execute("DELETE FROM main.structural_batches WHERE sequence=? AND sha256=?",(seq,witness)).rowcount!=1:
        raise a.GraphHeld("multi-batch reservation disappeared")
    db.execute("INSERT INTO main.structural_terminal VALUES(?,?,?)",(seq,witness,"aborted" if aborted else "settled"))
    # Bounded diagnostic replay cache. Durable snapshot page/feed/job receipts
    # remain authoritative after terminal cache eviction.
    db.execute("DELETE FROM main.structural_terminal WHERE sequence IN (SELECT sequence FROM main.structural_terminal ORDER BY sequence DESC LIMIT -1 OFFSET ?)",(TERMINAL_RETENTION,))
    fence(db)
    if db.execute("UPDATE main.dragon_graph_authority SET commit_sequence=commit_sequence+1 WHERE singleton=1").rowcount!=1:
        raise a.GraphHeld("root commit fence missing")


def verify(db):
    """Idle-state audit: no orphan lane receipts or reserved owner keys."""
    if not enabled(db):return
    assert_fence(db)
    if rows(db):raise a.GraphHeld("finish pending structural batches before full graph audit")
    if owners(db):raise a.GraphHeld("orphan structural owner reservations")
    if db.execute("SELECT COUNT(*) FROM main.structural_terminal").fetchone()[0]>TERMINAL_RETENTION:
        raise a.GraphHeld("terminal replay cache bound")
    seq=db.execute("SELECT sequence FROM main.dragon_graph_structural WHERE singleton=1").fetchone()[0]
    if db.execute("SELECT 1 FROM main.structural_terminal WHERE sequence>? OR sequence<=0 OR length(sha256)<>64 LIMIT 1",(seq,)).fetchone():
        raise a.GraphHeld("terminal sequence differs")
    for i in range(a.LANES):
        if db.execute("SELECT 1 FROM "+a._alias(i)+".structural_receipts LIMIT 1").fetchone():
            raise a.GraphHeld("orphan lane structural receipt")
