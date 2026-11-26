"""Physical evidence-edge graph partitions; canonical graph remains authority.

Each owner has ten independently writable edge stores. Canonical transactions
record dirty edge identities, then bounded catch-up copies exact edge records.
Traversal may use all ten only with a matching source snapshot and lineage.
No additional evidence rights, network access or primary graph migration.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import sqlite3
import time

from core.dragon_hoarder_bulk import owner_key
from core.dragon_lead_index_shards import bounds,_lane,HEX,LANES
from core.dragon_owner_shards import _open,_private,ShardHeld

FIELDS=("owner","id","parent","child","relation","subject","kind","title","witness","snapshot","first_seen","last_seen")
BATCH=512


class EdgeHeld(RuntimeError):
    pass


def _trigger(name,event,expr,when="1"):
    lane=_lane(expr+".id")
    return f"""CREATE TRIGGER IF NOT EXISTS {name} AFTER {event} ON lead_edges
    WHEN ({when}) AND EXISTS(SELECT 1 FROM lead_edge_enrollment WHERE owner={expr}.owner)
    BEGIN
      UPDATE lead_edge_versions SET revision=revision+1,stamp=lower(hex(randomblob(32))) WHERE owner={expr}.owner AND lane={lane};
      INSERT INTO lead_edge_dirty(owner,lane,id,revision)
        SELECT {expr}.owner,{lane},{expr}.id,revision FROM lead_edge_versions WHERE owner={expr}.owner AND lane={lane}
        ON CONFLICT(owner,lane,id) DO UPDATE SET revision=excluded.revision;
    END;"""


SOURCE_SCHEMA="""
CREATE TABLE IF NOT EXISTS lead_edge_enrollment(
 owner TEXT PRIMARY KEY,epoch TEXT NOT NULL,next_lane INTEGER NOT NULL CHECK(next_lane BETWEEN 0 AND 9),due INTEGER NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_edge_enrollment_due ON lead_edge_enrollment(due,owner);
CREATE TABLE IF NOT EXISTS lead_edge_versions(
 owner TEXT NOT NULL,lane INTEGER NOT NULL CHECK(lane BETWEEN 0 AND 9),revision INTEGER NOT NULL CHECK(revision>=0),
 stamp TEXT NOT NULL CHECK(length(stamp)=64),floor INTEGER NOT NULL CHECK(floor BETWEEN 0 AND revision),
 PRIMARY KEY(owner,lane)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS lead_edge_dirty(
 owner TEXT NOT NULL,lane INTEGER NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,
 PRIMARY KEY(owner,lane,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_edge_dirty_order ON lead_edge_dirty(owner,lane,revision,id);
"""+_trigger("lead_edge_partition_insert","INSERT","NEW")+_trigger("lead_edge_partition_update","UPDATE","NEW",
    " OR ".join("OLD."+name+" IS NOT NEW."+name for name in FIELDS[2:])
)+_trigger("lead_edge_partition_delete","DELETE","OLD")

SCHEMA="""
CREATE TABLE IF NOT EXISTS edge_identity(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),owner TEXT NOT NULL,epoch TEXT NOT NULL,lane INTEGER NOT NULL,
 phase TEXT NOT NULL CHECK(phase IN ('scan','catchup')),cursor TEXT NOT NULL,
 revision INTEGER NOT NULL,stamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges(
 owner TEXT NOT NULL,id TEXT NOT NULL,parent TEXT NOT NULL,child TEXT NOT NULL,relation TEXT NOT NULL,
 subject TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,witness TEXT NOT NULL,snapshot TEXT,
 first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL,PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS edge_parent ON edges(owner,parent,id);
CREATE INDEX IF NOT EXISTS edge_child ON edges(owner,child,id);
CREATE INDEX IF NOT EXISTS edge_subject ON edges(owner,subject,id);
"""


def _root():
    value=os.getenv("SKL_DRAGON_LEAD_EDGE_ROOT","").strip()
    p=Path(value)
    if not value or not p.is_absolute() or any(x.is_symlink() for x in (p,*p.parents)) or not p.is_dir():
        raise EdgeHeld("private edge root required")
    info=p.stat()
    if os.name=="posix" and (info.st_uid!=os.getuid() or info.st_mode&0o077):
        raise EdgeHeld("private edge root required")
    return p


@contextmanager
def _file(owner,epoch,lane,*,create=False):
    bounds(lane)
    if any(not isinstance(x,str) or not HEX.fullmatch(x) for x in (owner,epoch)):
        raise EdgeHeld("edge partition identity")
    directory=_root()/("edges-"+owner+"-"+epoch)
    if create:
        try:directory.mkdir(mode=0o700)
        except FileExistsError:pass
    if directory.is_symlink() or not directory.is_dir():raise EdgeHeld("edge directory unavailable")
    st=directory.stat()
    if os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077):raise EdgeHeld("edge directory permissions")
    path=directory/("edge-"+str(lane)+".sqlite3")
    if create and not path.exists():
        try:_private(path,create=True)
        except FileExistsError:pass
    with _open(path) as db:
        if create:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        yield db


def enroll(graph,scope,*,acknowledged=False,reset=False):
    if acknowledged is not True or type(reset) is not bool:raise ValueError("edge metadata acknowledgement")
    _root();owner=owner_key(scope)
    with graph._db() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            if not db.execute("SELECT 1 FROM lead_owner WHERE owner=?",(owner,)).fetchone():raise LookupError("lead owner missing")
            prior=db.execute("SELECT epoch FROM lead_edge_enrollment WHERE owner=?",(owner,)).fetchone()
            if prior and not reset:epoch=prior[0]
            else:
                for table in ("lead_edge_dirty","lead_edge_versions","lead_edge_enrollment"):
                    db.execute("DELETE FROM "+table+" WHERE owner=?",(owner,))
                epoch=secrets.token_hex(32)
                db.execute("INSERT INTO lead_edge_enrollment VALUES(?,?,0,?)",(owner,epoch,int(time.time())))
                db.executemany("INSERT INTO lead_edge_versions VALUES(?,?,0,?,0)",
                    ((owner,lane,secrets.token_hex(32)) for lane in range(LANES)))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"enabled":True,"epoch":epoch,"physical_edge_partitions":LANES,"canonical_write_partitioned":False,"network_authorized":False}


def _version(db,owner,lane):
    row=db.execute("SELECT revision,stamp,floor FROM lead_edge_versions WHERE owner=? AND lane=?",(owner,lane)).fetchone()
    if not row:raise EdgeHeld("edge source revision missing")
    return row


def _identity(db,owner,epoch,lane):
    row=db.execute("SELECT * FROM edge_identity WHERE singleton=1").fetchone()
    if row and (row["owner"],row["epoch"],row["lane"])!=(owner,epoch,lane):raise EdgeHeld("edge shard identity differs")
    return row


def _replace(db,owner,identifier,row):
    if row is None:db.execute("DELETE FROM edges WHERE owner=? AND id=?",(owner,identifier))
    else:
        db.execute("INSERT OR REPLACE INTO edges VALUES("+",".join("?" for _ in FIELDS)+")",tuple(row))


def _step(source,owner,epoch,lane):
    version=_version(source,owner,lane);revision=version["revision"]
    low,high=bounds(lane);fields=",".join(FIELDS)
    with _file(owner,epoch,lane,create=True) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            state=_identity(db,owner,epoch,lane)
            if not state:
                db.execute("INSERT INTO edge_identity VALUES(1,?,?,?,'scan','',?,?)",(owner,epoch,lane,revision,version["stamp"]))
                state=_identity(db,owner,epoch,lane)
            if not version["floor"]<=state["revision"]<=revision or state["revision"]==revision and state["stamp"]!=version["stamp"]:
                raise EdgeHeld("edge lineage differs; reset required")
            if state["phase"]=="scan":
                rows=source.execute("SELECT "+fields+" FROM lead_edges WHERE owner=? AND id>=? AND id<? AND id>? ORDER BY id LIMIT ?",
                    (owner,low,high,state["cursor"],BATCH)).fetchall()
                for row in rows:_replace(db,owner,row["id"],row)
                db.execute("UPDATE edge_identity SET cursor=?,phase=? WHERE singleton=1",
                    (rows[-1]["id"] if rows else state["cursor"],"catchup" if len(rows)<BATCH else "scan"))
            else:
                rows=source.execute("SELECT id,revision FROM lead_edge_dirty WHERE owner=? AND lane=? AND revision>? ORDER BY revision,id LIMIT ?",
                    (owner,lane,state["revision"],BATCH)).fetchall()
                for change in rows:
                    row=source.execute("SELECT "+fields+" FROM lead_edges WHERE owner=? AND id=?",(owner,change["id"])).fetchone()
                    _replace(db,owner,change["id"],row)
                through=rows[-1]["revision"] if len(rows)==BATCH else revision
                db.execute("UPDATE edge_identity SET revision=?,stamp=? WHERE singleton=1",(through,version["stamp"] if through==revision else ""))
            final=_identity(db,owner,epoch,lane)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"lane":lane,"processed":len(rows),"phase":final["phase"],"revision":final["revision"],"source_revision":revision}


def pulse(graph):
    _root();now=int(time.time())
    with graph._db() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            job=db.execute("SELECT * FROM lead_edge_enrollment WHERE due<=? ORDER BY due,owner LIMIT 1",(now,)).fetchone()
            if job is None:
                db.execute("COMMIT");return {"processed":0}
            owner,epoch,lane=job["owner"],job["epoch"],job["next_lane"]
            db.execute("UPDATE lead_edge_enrollment SET next_lane=?,due=? WHERE owner=? AND epoch=?",
                ((lane+1)%LANES,now+1,owner,epoch))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        db.execute("BEGIN")
        try:
            result=_step(db,owner,epoch,lane)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        if result["phase"]=="catchup" and result["revision"]==result["source_revision"]:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM lead_edge_enrollment WHERE owner=? AND epoch=?",(owner,epoch)).fetchone():
                    db.execute("UPDATE lead_edge_versions SET floor=MAX(floor,?) WHERE owner=? AND lane=?",(result["revision"],owner,lane))
                    db.execute("DELETE FROM lead_edge_dirty WHERE owner=? AND lane=? AND revision<=?",(owner,lane,result["revision"]))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
    return {**result,"network_authorized":False}


def lookup(db,owner,lead,*,field,lower,limit):
    if field not in {"parent","child"} or type(limit) is not int or not 1<=limit<=100:raise ValueError("edge search bounds")
    enrollment=db.execute("SELECT epoch FROM lead_edge_enrollment WHERE owner=?",(owner,)).fetchone()
    if not enrollment:raise EdgeHeld("edge projection not enrolled")
    epoch=enrollment[0];deadline=time.monotonic()+2;found={}
    for lane in range(LANES):
        if time.monotonic()>deadline:raise EdgeHeld("edge lookup deadline")
        source=_version(db,owner,lane)
        with _file(owner,epoch,lane) as part:
            part.execute("BEGIN")
            try:
                identity=_identity(part,owner,epoch,lane)
                if not identity or identity["phase"]!="catchup" or identity["revision"]!=source["revision"] or identity["stamp"]!=source["stamp"]:
                    raise EdgeHeld("edge projection not current")
                part.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
                rows=part.execute("SELECT "+",".join(FIELDS)+" FROM edges WHERE owner=? AND "+field+"=? AND id>? ORDER BY id LIMIT ?",
                    (owner,lead,lower,limit+1)).fetchall()
                low,high=bounds(lane)
                for row in rows:
                    identifier=row["id"]
                    if not HEX.fullmatch(identifier) or not low<=identifier<high or identifier in found:
                        raise EdgeHeld("edge candidate partition differs")
                    found[identifier]=tuple(row)
                part.execute("COMMIT")
            except BaseException:
                if part.in_transaction:part.execute("ROLLBACK")
                raise
    picked=sorted(found)[:limit+1]
    if not picked:return []
    # Snapshot revocation/expiry state is joined only from canonical source.
    rows=db.execute("SELECT e.*,s.state AS snapshot_state,s.expires_at AS snapshot_expires_at FROM lead_edges e LEFT JOIN lead_snapshots s ON s.owner=e.owner AND s.id=e.snapshot WHERE e.owner=? AND e.id IN ("+
        ",".join("?" for _ in picked)+") ORDER BY e.id",[owner,*picked]).fetchall()
    if [r["id"] for r in rows]!=picked or any(tuple(r[k] for k in FIELDS)!=found[r["id"]] or r[field]!=lead for r in rows):
        raise EdgeHeld("canonical edge witness differs")
    return rows


def main():
    import argparse
    import json
    from core.dragon_corpus_runtime import _path
    from core.dragon_lead_graph import LeadGraph
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-json",required=True)
    parser.add_argument("--acknowledge-metadata-index",action="store_true")
    parser.add_argument("--reset-derived-edges",action="store_true")
    args=parser.parse_args()
    path,_=_private(Path(args.scope_json))
    if path.stat().st_size>4096:raise EdgeHeld("scope file bound")
    scope=json.loads(path.read_bytes())
    print(json.dumps(enroll(LeadGraph(_path(scope=scope)),scope,
        acknowledged=args.acknowledge_metadata_index,reset=args.reset_derived_edges)))


if __name__=="__main__":main()
