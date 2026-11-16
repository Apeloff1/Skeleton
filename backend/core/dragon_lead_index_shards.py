"""Incremental ten-file owner-local search projection.

Canonical lead_nodes and their owner-scoped revisions remain authoritative.
Only derived search metadata is stored. Incomplete, stale or damaged indexes
fall back to the existing canonical search. This never grants capture rights.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from core.dragon_hoarder_bulk import owner_key
from core.dragon_owner_shards import _private,_open,ShardHeld

LANES=10
BATCH=512
ZERO="0"*64
FIELDS=("id","owner","title","url","kind","family","host","state","next_review")
HEX=re.compile(r"[0-9a-f]{64}\Z")


class IndexHeld(RuntimeError):
    """Projection unavailable or stale; canonical lookup must be used."""


def bounds(lane):
    if type(lane) is not int or not 0<=lane<LANES:raise ValueError("index lane")
    a=(lane*65536+LANES-1)//LANES;b=((lane+1)*65536+LANES-1)//LANES
    return format(a,"04x"),format(b,"04x") if b<65536 else "g"


def _lane(expr):
    pairs=[("WHEN "+expr+" < '"+bounds(i)[1]+"' THEN "+str(i)) for i in range(LANES-1)]
    return "(CASE "+" ".join(pairs)+" ELSE 9 END)"


def _trigger(name,event,expr,when):
    lane=_lane(expr+".id")
    return f"""CREATE TRIGGER IF NOT EXISTS {name} AFTER {event} ON lead_nodes
    WHEN ({when}) AND EXISTS(SELECT 1 FROM lead_index_enrollment WHERE owner={expr}.owner)
    BEGIN
      UPDATE lead_index_versions SET revision=revision+1,stamp=lower(hex(randomblob(32))) WHERE owner={expr}.owner AND lane={lane};
      INSERT INTO lead_index_changes(owner,lane,id,revision)
       SELECT {expr}.owner,{lane},{expr}.id,revision FROM lead_index_versions WHERE owner={expr}.owner AND lane={lane}
       ON CONFLICT(owner,lane,id) DO UPDATE SET revision=excluded.revision;
    END;"""


SOURCE_SCHEMA="""
CREATE TABLE IF NOT EXISTS lead_index_enrollment(
 owner TEXT PRIMARY KEY,epoch TEXT NOT NULL CHECK(length(epoch)=64),next_lane INTEGER NOT NULL CHECK(next_lane BETWEEN 0 AND 9),
 due INTEGER NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_index_due ON lead_index_enrollment(due,owner);
CREATE TABLE IF NOT EXISTS lead_index_versions(
 owner TEXT NOT NULL,lane INTEGER NOT NULL CHECK(lane BETWEEN 0 AND 9),revision INTEGER NOT NULL CHECK(revision>=0),
 stamp TEXT NOT NULL CHECK(length(stamp)=64),floor INTEGER NOT NULL CHECK(floor>=0 AND floor<=revision),
 PRIMARY KEY(owner,lane)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS lead_index_changes(
 owner TEXT NOT NULL,lane INTEGER NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL CHECK(revision>=0),
 PRIMARY KEY(owner,lane,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_index_change_order ON lead_index_changes(owner,lane,revision,id);
"""+_trigger("lead_index_insert","INSERT","NEW","1")+_trigger(
    "lead_index_update","UPDATE OF title,url,kind,family,host,state,next_review","NEW",
    "OLD.title IS NOT NEW.title OR OLD.url IS NOT NEW.url OR OLD.kind IS NOT NEW.kind OR OLD.family IS NOT NEW.family OR OLD.host IS NOT NEW.host OR OLD.state IS NOT NEW.state OR OLD.next_review IS NOT NEW.next_review"
)+_trigger("lead_index_delete","DELETE","OLD","1")

SCHEMA="""
CREATE TABLE IF NOT EXISTS identity(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),owner TEXT NOT NULL,epoch TEXT NOT NULL,lane INTEGER NOT NULL,
 phase TEXT NOT NULL CHECK(phase IN ('scan','catchup')),cursor TEXT NOT NULL,revision INTEGER NOT NULL,stamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes(
 id TEXT PRIMARY KEY,owner TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,kind TEXT NOT NULL,
 family TEXT NOT NULL,host TEXT NOT NULL,state TEXT NOT NULL,next_review INTEGER NOT NULL,
 fts_row INTEGER NOT NULL UNIQUE
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS nodes_state ON nodes(state,id);
CREATE INDEX IF NOT EXISTS nodes_family ON nodes(state,family,id);
CREATE INDEX IF NOT EXISTS nodes_host ON nodes(state,host,id);
CREATE INDEX IF NOT EXISTS nodes_due ON nodes(state,next_review,id);
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(owner,id UNINDEXED,title,url,kind,family,
 tokenize='unicode61 remove_diacritics 2');
"""


def _root():
    raw=os.getenv("SKL_DRAGON_LEAD_INDEX_ROOT","").strip()
    if not raw:raise IndexHeld("physical lead index not configured")
    path=Path(raw)
    if not path.is_absolute() or any(x.is_symlink() for x in (path,*path.parents)) or not path.is_dir():
        raise IndexHeld("private index root required")
    st=path.stat()
    if os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077):
        raise IndexHeld("private index root required")
    return path


def _directory(owner,epoch,*,create=False):
    if not all(isinstance(k,str) and HEX.fullmatch(k) for k in (owner,epoch)):raise IndexHeld("projection identity")
    root=_root()
    path=root/(owner+"-"+epoch)
    if create:
        try:path.mkdir(mode=0o700)
        except FileExistsError:pass
    if path.is_symlink() or not path.is_dir():raise IndexHeld("projection directory unavailable")
    st=path.stat()
    if os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077):raise IndexHeld("projection directory permissions")
    return path


@contextmanager
def _shard(owner,epoch,lane,*,create=False):
    bounds(lane)
    path=_directory(owner,epoch,create=create)/("lead-"+str(lane)+".sqlite3")
    if create and not path.exists():
        try:_private(path,create=True)
        except FileExistsError:pass
    with _open(path) as db:
        if create:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        yield db


def enroll(graph,scope,*,acknowledged=False,reset=False):
    """Explicit operator opt-in; source generation is never reused after reset."""
    if acknowledged is not True or type(reset) is not bool:raise ValueError("metadata index acknowledgement")
    owner=owner_key(scope);_root()
    from core.dragon_graph_authority import active
    with graph._db() as db:
        if active(db):raise ValueError("derived projection redundant in canonical graph mode")
        db.execute("BEGIN IMMEDIATE")
        try:
            if not db.execute("SELECT 1 FROM lead_owner WHERE owner=?",(owner,)).fetchone():
                raise LookupError("lead owner missing")
            row=db.execute("SELECT epoch FROM lead_index_enrollment WHERE owner=?",(owner,)).fetchone()
            if row and not reset:epoch=row[0]
            else:
                for name in ("lead_index_changes","lead_index_versions","lead_index_enrollment"):
                    db.execute("DELETE FROM "+name+" WHERE owner=?",(owner,))
                epoch=secrets.token_hex(32)
                db.execute("INSERT INTO lead_index_enrollment VALUES(?,?,0,?)",(owner,epoch,int(time.time())))
                db.executemany("INSERT INTO lead_index_versions VALUES(?,?,0,?,0)",
                    ((owner,n,secrets.token_hex(32)) for n in range(LANES)))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"enabled":True,"shards":LANES,"epoch":epoch,"network_authorized":False}


def _replace(db,row,identifier):
    prior=db.execute("SELECT fts_row FROM nodes WHERE id=?",(identifier,)).fetchone()
    if prior:
        db.execute("DELETE FROM search WHERE rowid=?",(prior[0],))
        db.execute("DELETE FROM nodes WHERE id=?",(identifier,))
    if row is not None:
        posted=db.execute("INSERT INTO search VALUES(?,?,?,?,?,?)",
            (row["owner"],row["id"],row["title"],row["url"],row["kind"],row["family"]))
        db.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?)",(*tuple(row),posted.lastrowid))


def _version(db,owner,lane):
    r=db.execute("SELECT revision,stamp,floor FROM lead_index_versions WHERE owner=? AND lane=?",(owner,lane)).fetchone()
    if not r:raise IndexHeld("source revision missing")
    return r


def _identity(db,owner,epoch,lane):
    row=db.execute("SELECT * FROM identity WHERE singleton=1").fetchone()
    if row and (row["owner"],row["epoch"],row["lane"])!=(owner,epoch,lane):
        raise IndexHeld("projection identity differs")
    return row


def _pulse_lane(src,owner,epoch,lane):
    """One bounded scan or delta batch, against one source read snapshot."""
    low,high=bounds(lane)
    source=_version(src,owner,lane);version=source['revision']
    with _shard(owner,epoch,lane,create=True) as dst:
        dst.execute("BEGIN IMMEDIATE")
        try:
            current=_identity(dst,owner,epoch,lane)
            if not current:
                dst.execute("INSERT INTO identity VALUES(1,?,?,?,'scan','',?,?)",(owner,epoch,lane,version,source["stamp"]))
                current=_identity(dst,owner,epoch,lane)
            if current["revision"]>version or current["revision"]<source["floor"]:
                raise IndexHeld("projection watermark outside retained source history; reset required")
            if current["revision"]==version and current["stamp"]!=source["stamp"]:
                raise IndexHeld("projection source lineage differs; reset required")
            fields=",".join(FIELDS)
            if current["phase"]=="scan":
                rows=src.execute("SELECT "+fields+" FROM lead_nodes WHERE owner=? AND id>=? AND id<? AND id>? ORDER BY id LIMIT ?",
                    (owner,low,high,current["cursor"],BATCH)).fetchall()
                for row in rows:_replace(dst,row,row["id"])
                cursor=rows[-1]["id"] if rows else current["cursor"]
                dst.execute("UPDATE identity SET cursor=?,phase=? WHERE singleton=1",
                    (cursor,"catchup" if len(rows)<BATCH else "scan"))
                processed=len(rows)
            else:
                rows=src.execute("SELECT id,revision FROM lead_index_changes WHERE owner=? AND lane=? AND revision>? ORDER BY revision,id LIMIT ?",
                    (owner,lane,current["revision"],BATCH)).fetchall()
                for change in rows:
                    row=src.execute("SELECT "+fields+" FROM lead_nodes WHERE owner=? AND id=?",(owner,change["id"])).fetchone()
                    _replace(dst,row,change["id"])
                watermark=rows[-1]["revision"] if len(rows)==BATCH else version
                dst.execute("UPDATE identity SET revision=?,stamp=? WHERE singleton=1",
                    (watermark,source["stamp"] if watermark==version else ""))
                processed=len(rows)
            final=_identity(dst,owner,epoch,lane)
            dst.execute("COMMIT")
        except BaseException:
            if dst.in_transaction:dst.execute("ROLLBACK")
            raise
    return {"processed":processed,"phase":final["phase"],"revision":final["revision"],
            "source_revision":version,"stamp":final["stamp"],"lane":lane}


def pulse(graph):
    """Advance one enrolled owner/lane per maintenance invocation."""
    _root()
    now=int(time.time())
    with graph._db() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            item=db.execute("SELECT * FROM lead_index_enrollment WHERE due<=? ORDER BY due,owner LIMIT 1",(now,)).fetchone()
            if item is None:
                db.execute("COMMIT");return {"processed":0,"configured":True}
            owner,epoch,lane=item["owner"],item["epoch"],item["next_lane"]
            db.execute("UPDATE lead_index_enrollment SET next_lane=?,due=? WHERE owner=? AND epoch=?",
                ((lane+1)%LANES,now+1,owner,epoch))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        db.execute("BEGIN")
        try:
            result=_pulse_lane(db,owner,epoch,lane)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        # Prune only already-applied deltas after the projection transaction
        # has committed. A missing or replaced derived file must be rebuilt
        # from scan, never trust its old watermark.
        if result["phase"]=="catchup" and result["revision"]==result["source_revision"]:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM lead_index_enrollment WHERE owner=? AND epoch=?",(owner,epoch)).fetchone():
                    db.execute("UPDATE lead_index_versions SET floor=MAX(floor,?) WHERE owner=? AND lane=?",
                        (result["revision"],owner,lane))
                    db.execute("DELETE FROM lead_index_changes WHERE owner=? AND lane=? AND revision<=?",(owner,lane,result["revision"]))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
    return {**result,"configured":True,"network_authorized":False}


def lookup(db,owner,terms,*,state,family,host,lower,cutoff,limit):
    """Merge exact, independently indexed lane candidates; hydrate canonically.

    Caller must hold a source read transaction to fence all ten revisions.
    """
    if not terms:raise IndexHeld("text query required")
    row=db.execute("SELECT epoch FROM lead_index_enrollment WHERE owner=?",(owner,)).fetchone()
    if not row:raise IndexHeld("owner projection not enrolled")
    epoch=row[0];deadline=time.monotonic()+2
    ids=[];witnesses={}
    query='owner:"'+owner+'" AND '+' AND '.join('"'+term+'"' for term in terms)
    for lane in range(LANES):
        if time.monotonic()>deadline:raise IndexHeld('projection query deadline')
        expected=_version(db,owner,lane)
        with _shard(owner,epoch,lane) as shard:
            shard.execute("BEGIN")
            try:
                identity=_identity(shard,owner,epoch,lane)
                if not identity or identity["phase"]!="catchup" or identity["revision"]!=expected["revision"] or identity["stamp"]!=expected["stamp"]:
                    raise IndexHeld("projection not current")
                where=["n.owner=?","n.state=?","n.id>?","search MATCH ?"]
                values=[owner,state,lower,query]
                if family:where.append("n.family=?");values.append(family)
                if host:where.append("n.host=?");values.append(host)
                if cutoff is not None:where.append("n.next_review<=?");values.append(cutoff)
                values.append(limit+1)
                shard.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
                found=shard.execute("SELECT "+",".join("n."+field for field in FIELDS)+" FROM nodes n JOIN search f ON n.fts_row=f.rowid WHERE "+
                    " AND ".join(where)+" ORDER BY n.id LIMIT ?",values).fetchall()
                for item in found:
                    if not HEX.fullmatch(item[0]) or not bounds(lane)[0]<=item[0]<bounds(lane)[1]:
                        raise IndexHeld("projection candidate identity")
                    ids.append(item[0]);witnesses[item[0]]=tuple(item)
                shard.execute("COMMIT")
            except BaseException:
                if shard.in_transaction:shard.execute("ROLLBACK")
                raise
    if len(set(ids))!=len(ids):raise IndexHeld("duplicate projection candidates")
    picked=sorted(ids)[:limit+1]
    if not picked:return []
    rows=db.execute("SELECT * FROM lead_nodes WHERE owner=? AND id IN ("+
        ",".join("?" for _ in picked)+") ORDER BY id",[owner,*picked]).fetchall()
    if [r["id"] for r in rows]!=picked or any(r["state"]!=state or family and r["family"]!=family or
        host and r["host"]!=host or cutoff is not None and r["next_review"]>cutoff for r in rows):
        raise IndexHeld("canonical candidate differs")
    if any(tuple(row[field] for field in FIELDS)!=witnesses[row["id"]] for row in rows):
        raise IndexHeld("canonical search witness differs")
    # Only canonical rows leave the projection. The derived index does not
    # grant evidence rights, and same-UID malicious modifications are outside
    # this local operator-controlled cache boundary.
    return rows


def main():
    import argparse
    from core.dragon_lead_graph import LeadGraph
    from core.dragon_corpus_runtime import _path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-json",required=True)
    parser.add_argument("--acknowledge-metadata-index",action="store_true")
    parser.add_argument("--pulse",type=int,default=1)
    parser.add_argument("--reset-derived-index",action="store_true")
    args=parser.parse_args()
    if not 0<=args.pulse<=1000:parser.error("bounded pulse count")
    scope_path,_=_private(Path(args.scope_json))
    if scope_path.stat().st_size>4096:raise IndexHeld("scope file bound")
    scope=json.loads(scope_path.read_bytes())
    graph=LeadGraph(_path(scope=scope))
    print(json.dumps(enroll(graph,scope,acknowledged=args.acknowledge_metadata_index,reset=args.reset_derived_index)))
    for i in range(args.pulse):
        if i:time.sleep(1)
        print(json.dumps(pulse(graph)))


if __name__=="__main__":main()
