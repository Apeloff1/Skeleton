"""Independent, authoritative review transactions for physical graph lanes.

Only node disposition, next-review time and its immutable replay receipt
change here. Node/edge admission, quotas, grants and outbox settlement remain
in the coordinated graph transaction. Root policy is held under a shared
rollback-journal read lock until the selected lane commits.
"""
from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from pathlib import Path

from core import dragon_graph_authority as authority
from core.dragon_owner_shards import _open,_private,ShardHeld

VERSION=1
MAX_EVENTS_PER_OWNER_LANE=20_000_000
ROOT_SCHEMA="""CREATE TABLE dragon_graph_direct_writer(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),version INTEGER NOT NULL,
 epoch TEXT NOT NULL CHECK(length(epoch)=64)
)"""
EVENTS="""CREATE TABLE review_events(
 owner TEXT NOT NULL,id TEXT NOT NULL,lead TEXT NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('candidate','held','retired')),
 witness TEXT NOT NULL CHECK(length(witness)=64),created_at INTEGER NOT NULL,
 PRIMARY KEY(owner,id),FOREIGN KEY(owner,lead) REFERENCES nodes(owner,id)
) WITHOUT ROWID"""
COUNTS="""CREATE TABLE review_counts(owner TEXT PRIMARY KEY,total INTEGER NOT NULL CHECK(total>=0)) WITHOUT ROWID"""
WRITER="""CREATE TABLE writer_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 revision INTEGER NOT NULL CHECK(revision>=0))"""
SCHEMA=EVENTS+";"+COUNTS+";"+WRITER+";INSERT INTO writer_state VALUES(1,0);"


def enabled(db):
    if not authority.active(db):return False
    if not db.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name='dragon_graph_direct_writer'").fetchone():return False
    marker=db.execute("SELECT version,epoch FROM main.dragon_graph_direct_writer WHERE singleton=1").fetchone()
    if not marker or marker[0]!=VERSION or not authority.HEX.fullmatch(marker[1]):
        raise authority.GraphHeld("direct graph writer marker differs")
    layout_row=db.execute("SELECT layout FROM main.dragon_graph_authority WHERE singleton=1").fetchone()
    import json
    try:layout=json.loads(layout_row[0])
    except (TypeError,ValueError) as exc:raise authority.GraphHeld("graph layout invalid") from exc
    if not isinstance(layout,dict) or layout.get("epoch")!=marker[1]:
        raise authority.GraphHeld("direct writer epoch differs")
    return True


def configured(root):
    """Read-only mode discovery; legacy databases need not satisfy new private-path checks."""
    path=Path(root).absolute()
    if not path.exists():return False
    db=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=5,isolation_level=None)
    try:return enabled(db)
    finally:db.close()


def publish_marker(db,epoch):
    db.execute(ROOT_SCHEMA)
    db.execute("INSERT INTO main.dragon_graph_direct_writer VALUES(1,?,?)",(VERSION,epoch))


def install(root,*,offline_acknowledged=False):
    """Atomic offline upgrade of pre-existing canonical v1 graph layouts."""
    if offline_acknowledged is not True:raise authority.GraphHeld("stop every old writer first")
    root=Path(root)
    with authority._probe_connection(root) as db:
        if enabled(db):return {"installed":True,"replayed":True,"lanes":authority.LANES}
        layout=authority._layout(db,root)
        db.execute("BEGIN IMMEDIATE")
        try:
            if enabled(db):raise authority.GraphHeld("direct writer topology changed")
            for i in range(authority.LANES):
                alias=authority._alias(i)
                for name,definition in (("review_events",EVENTS),("review_counts",COUNTS),("writer_state",WRITER)):
                    if db.execute("SELECT 1 FROM "+alias+".sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():
                        raise authority.GraphHeld("unpublished direct writer tables exist")
                    db.execute(definition.replace("CREATE TABLE "+name,"CREATE TABLE "+alias+"."+name,1))
                db.execute("INSERT INTO "+alias+".writer_state VALUES(1,0)")
            publish_marker(db,layout["epoch"])
            authority._fence(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"installed":True,"replayed":False,"lanes":authority.LANES}


@contextmanager
def _lane_db(root,layout,index,root_identity):
    path,identity=_private(Path(layout["paths"][index]))
    if _private(root)[1]!=root_identity or identity==root_identity:raise authority.GraphHeld("lane aliases root or root replaced")
    with _open(path) as db:
        if _private(path)[1]!=identity:raise authority.GraphHeld("lane replaced")
        if db.execute("PRAGMA journal_mode").fetchone()[0].lower()!="delete":
            raise authority.GraphHeld("lane writer journal differs")
        db.execute("PRAGMA synchronous=EXTRA")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("BEGIN IMMEDIATE")
        try:
            row=db.execute("SELECT epoch,lane FROM graph_identity WHERE singleton=1").fetchone()
            if not row or tuple(row)!=(layout["epoch"],index):raise authority.GraphHeld("lane writer identity differs")
            if not db.execute("SELECT 1 FROM writer_state WHERE singleton=1").fetchone():
                raise authority.GraphHeld("lane writer state missing")
            yield db
            if _private(path)[1]!=identity or _private(root)[1]!=root_identity:
                raise authority.GraphHeld("graph root or lane replaced before commit")
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise


def review(root,owner,lead,*,identity,witness,decision,now,due):
    """Return None only when independent writers were never activated.

    The root read transaction protects owner enablement, directory membership,
    topology and legacy receipts. No root mutation is required by this path.
    """
    if any(not isinstance(k,str) or not authority.HEX.fullmatch(k) for k in (owner,lead,identity,witness)):
        raise ValueError("review identity")
    if decision not in {"candidate","held","retired"} or type(now) is not int or type(due) is not int or not 900<=due-now<=90*86400:
        raise ValueError("review bounds")
    root,root_identity=_private(Path(root))
    with _open(root) as policy:
        policy.execute("BEGIN")
        try:
            if not enabled(policy):
                policy.execute("COMMIT");return None
            if policy.execute("PRAGMA journal_mode").fetchone()[0].lower()!="delete":
                raise authority.GraphHeld("root writer policy journal differs")
            layout=authority._layout(policy,root)
            admission=policy.execute("SELECT enabled FROM lead_owner WHERE owner=?",(owner,)).fetchone()
            if not admission or not admission[0]:raise authority.GraphHeld("lead expansion disabled")
            if not policy.execute("SELECT 1 FROM lead_node_directory WHERE owner=? AND id=?",(owner,lead)).fetchone():
                raise LookupError("lead missing")
            prior=policy.execute("SELECT lead,decision,reason FROM lead_review_events WHERE owner=? AND id=?",(owner,identity)).fetchone()
            index=authority.lane(lead)
            with _lane_db(root,layout,index,root_identity) as db:
                node=db.execute("SELECT state,next_review FROM nodes WHERE owner=? AND id=?",(owner,lead)).fetchone()
                if not node:raise authority.GraphHeld("canonical node missing from selected lane")
                local=db.execute("SELECT lead,decision,witness FROM review_events WHERE owner=? AND id=?",(owner,identity)).fetchone()
                expected=(lead,decision,witness)
                if prior and local:raise authority.GraphHeld("duplicate root and lane replay authority")
                replay=prior or local
                if replay:
                    if tuple(replay)!=expected:raise authority.GraphHeld("lead review replay differs")
                else:
                    count=db.execute("SELECT total FROM review_counts WHERE owner=?",(owner,)).fetchone()
                    if count is None:
                        actual=db.execute("SELECT COUNT(*) FROM review_events WHERE owner=?",(owner,)).fetchone()[0]
                        db.execute("INSERT INTO review_counts VALUES(?,?)",(owner,actual))
                    else:actual=count[0]
                    if actual>=MAX_EVENTS_PER_OWNER_LANE:raise authority.GraphHeld("local review receipt quota")
                    if db.execute("UPDATE nodes SET state=?,next_review=? WHERE owner=? AND id=?",(decision,due,owner,lead)).rowcount!=1:
                        raise authority.GraphHeld("selected canonical node vanished")
                    db.execute("INSERT INTO review_events VALUES(?,?,?,?,?,?)",(owner,identity,lead,decision,witness,now))
                    db.execute("UPDATE review_counts SET total=total+1 WHERE owner=?",(owner,))
                    db.execute("UPDATE writer_state SET revision=revision+1 WHERE singleton=1")
                revision=db.execute("SELECT revision FROM writer_state WHERE singleton=1").fetchone()[0]
            policy.execute("COMMIT")
        except BaseException:
            if policy.in_transaction:policy.execute("ROLLBACK")
            raise
    return {"lead_id":lead,"decision":decision,"verified":False,"network_authorized":False,
            "independent_writer":True,"writer_lane":index,"lane_revision":revision,"replayed":bool(replay)}


def verify(db):
    """Full audit for local replay custody and exact per-owner counts."""
    if not enabled(db):return
    for i in range(authority.LANES):
        alias=authority._alias(i)
        state=db.execute("SELECT revision FROM "+alias+".writer_state WHERE singleton=1").fetchone()
        if not state:raise authority.GraphHeld("local writer state missing")
        events=db.execute("SELECT COUNT(*) FROM "+alias+".review_events").fetchone()[0]
        if events!=state[0]:raise authority.GraphHeld("local review sequence differs")
        for row in authority._iter(db,"SELECT owner,lead,id,witness FROM "+alias+".review_events"):
            if authority.lane(row["lead"])!=i or any(not authority.HEX.fullmatch(row[k]) for k in ("owner","id","witness")):
                raise authority.GraphHeld("local review identity differs")
            if db.execute("SELECT 1 FROM main.lead_review_events WHERE owner=? AND id=?",(row["owner"],row["id"])).fetchone():
                raise authority.GraphHeld("duplicate review authority")
        actual="SELECT owner,COUNT(*) AS n FROM "+alias+".review_events GROUP BY owner"
        counts=alias+".review_counts"
        if db.execute("WITH totals AS ("+actual+") SELECT 1 FROM totals t LEFT JOIN "+counts+" c ON c.owner=t.owner WHERE c.total IS NULL OR c.total<>t.n LIMIT 1").fetchone():
            raise authority.GraphHeld("local review counter differs")
        if db.execute("WITH totals AS ("+actual+") SELECT 1 FROM "+counts+" c LEFT JOIN totals t ON t.owner=c.owner WHERE c.total<>COALESCE(t.n,0) LIMIT 1").fetchone():
            raise authority.GraphHeld("local review counter orphan")
