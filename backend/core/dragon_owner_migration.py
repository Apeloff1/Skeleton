"""Offline, restartable root-to-lane migration of one complete canonical owner.

No row-id or identity regeneration except internal FTS row ids. No cross-file
atomicity is assumed: the root journal gates runtime until exact target
readback and a single root transaction publish the route and remove originals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from core.dragon_hoarder_bulk import owner_key
from core.dragon_owner_shards import (
    LANES,ShardHeld,_layout,_open,_plane,_private,_table,_target,
)

JOURNAL="""CREATE TABLE IF NOT EXISTS dragon_owner_migrations(
 plane TEXT NOT NULL,owner TEXT NOT NULL,destination INTEGER NOT NULL,
 topology_id TEXT NOT NULL,source_digest TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('copying','complete')),
 created_at INTEGER NOT NULL,finished_at INTEGER,
 PRIMARY KEY(plane,owner)
) WITHOUT ROWID"""
CORPUS_TABLES=(
    "counters","games","aliases","sources","game_source_counts","observations",
    "release_facets","capture_bindings","release_queue_counts","release_imports",
    "release_jobs","lead_release_outbox","lead_owner","lead_lane_counts","lead_nodes",
    "lead_edges","lead_dataset_candidates","lead_dynamic_targets","lead_snapshots",
    "lead_snapshot_pages","lead_expand_jobs","lead_review_events","media_objects",
)
MANIFEST_TABLES=("manifest_counts","manifests","chunks","placements","manifest_garbage")
FTS_TABLES=("game_search","lead_fts")
DERIVED_TABLES=("lead_index_changes","lead_index_versions","lead_index_enrollment",
    "lead_edge_dirty","lead_edge_versions","lead_edge_enrollment")
PAGE=256


def _quote(name):
    if not isinstance(name,str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",name):
        raise ShardHeld("unsafe schema identifier")
    return '"'+name+'"'


def _columns(db,table):
    return [r["name"] for r in db.execute("PRAGMA table_info("+_quote(table)+")")]


def _initialize(db,plane):
    if plane=="corpus":
        from core.dragon_game_corpus import SCHEMA as corpus
        from core.dragon_release_queue import SCHEMA as release
        from core.dragon_lead_graph import SCHEMA as leads
        from core.dragon_media_archive import SCHEMA as media
        for schema in (corpus,release,leads,media):db.executescript(schema)
    else:
        from core.dragon_hoarder_manifests import SCHEMA
        db.executescript(SCHEMA)
        db.execute("CREATE TABLE IF NOT EXISTS manifest_configuration(singleton INTEGER PRIMARY KEY CHECK(singleton=1),volumes TEXT NOT NULL)")
    db.execute("PRAGMA foreign_keys=ON")


def _unknown_owner_data(db,owner,plane):
    allowed=set(CORPUS_TABLES+FTS_TABLES+DERIVED_TABLES+("source_locator_fts","source_locator_rows","world_subscriptions","world_origin_guard")) if plane=="corpus" else set(MANIFEST_TABLES)
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        table=row[0]
        if table in allowed or table.startswith(("sqlite_","dragon_shard_","dragon_owner_")):continue
        if "owner" in _columns(db,table) and db.execute("SELECT 1 FROM "+_quote(table)+" WHERE owner=? LIMIT 1",(owner,)).fetchone():
            raise ShardHeld("unrecognized owner data table: "+table)


def _rows(db,table,owner):
    if not _table(db,table):return
    cols=_columns(db,table)
    if "owner" not in cols:raise ShardHeld("owner column missing")
    schema=db.execute("PRAGMA table_info("+_quote(table)+")").fetchall()
    primary=[r["name"] for r in sorted(schema,key=lambda x:x["pk"]) if r["pk"]]
    order=primary or cols
    sql="SELECT "+",".join(map(_quote,cols))+" FROM "+_quote(table)+" WHERE owner=? ORDER BY "+",".join(map(_quote,order))
    cursor=db.execute(sql,(owner,))
    while batch:=cursor.fetchmany(PAGE):
        yield from (tuple(row) for row in batch)


def _locators(db,owner):
    if not _table(db,"source_locator_rows"):
        return
    if not _table(db,"source_locator_fts"):raise ShardHeld("source FTS missing")
    cursor=db.execute("""SELECT i.owner,i.game,i.source,i.indexed_digest,f.title,f.locator,f.category
        FROM source_locator_rows i JOIN source_locator_fts f ON i.fts_row=f.rowid
        WHERE i.owner=? AND f.owner=i.owner AND f.game=i.game AND f.source=i.source
        ORDER BY i.owner,i.game,i.source""",(owner,))
    expected=db.execute("SELECT COUNT(*) FROM source_locator_rows WHERE owner=?",(owner,)).fetchone()[0]
    fts_count=db.execute("SELECT COUNT(*) FROM source_locator_fts WHERE owner=?",(owner,)).fetchone()[0]
    seen=0
    while batch:=cursor.fetchmany(PAGE):
        for row in batch:
            seen+=1
            yield tuple(row)
    if seen!=expected or seen!=fts_count:raise ShardHeld("source locator join incomplete")


def _groups(plane):
    return CORPUS_TABLES+FTS_TABLES+("source_locator_pair",) if plane=="corpus" else MANIFEST_TABLES


def _group_rows(db,table,owner):
    if table=="source_locator_pair":return _locators(db,owner)
    return _rows(db,table,owner)


def _fingerprint(db,owner,plane):
    _unknown_owner_data(db,owner,plane)
    total=0
    counts={}
    h=hashlib.sha256()
    def feed(value):
        raw=json.dumps(value,ensure_ascii=True,separators=(",",":"),allow_nan=False).encode()
        h.update(len(raw).to_bytes(8,"big"));h.update(raw)
    for table in _groups(plane):
        feed(table)
        columns=_columns(db,table) if table!="source_locator_pair" else []
        feed(columns)
        count=0
        for row in _group_rows(db,table,owner):
            feed(row);count+=1
        counts[table]=count;total+=count
        feed(count)
    return h.hexdigest(),total,counts


def _copy(src,dst,owner,plane):
    for table in _groups(plane):
        if table=="source_locator_pair":
            for o,g,i,d,title,url,category in _locators(src,owner):
                cur=dst.execute("INSERT INTO source_locator_fts(owner,game,source,title,locator,category) VALUES(?,?,?,?,?,?)",(o,g,i,title,url,category))
                dst.execute("INSERT INTO source_locator_rows VALUES(?,?,?,?,?)",(o,g,i,cur.lastrowid,d))
            continue
        cols=_columns(src,table)
        if cols!=_columns(dst,table):raise ShardHeld("source/destination schema mismatch")
        sql="INSERT INTO "+_quote(table)+"("+",".join(map(_quote,cols))+") VALUES("+",".join("?" for _ in cols)+")"
        dst.executemany(sql,_group_rows(src,table,owner))
    # Derived migration cursors are per-file, not per-owner. Reset to ensure
    # incomplete migrated backfills cannot be skipped by the destination.
    if plane=="corpus":dst.execute("DELETE FROM corpus_migration")


def _remove(db,owner,plane):
    if plane=="corpus":
        for name in DERIVED_TABLES:db.execute("DELETE FROM "+_quote(name)+" WHERE owner=?",(owner,))
        db.execute("DELETE FROM source_locator_rows WHERE owner=?",(owner,))
        db.execute("DELETE FROM source_locator_fts WHERE owner=?",(owner,))
        for table in FTS_TABLES:db.execute("DELETE FROM "+_quote(table)+" WHERE owner=?",(owner,))
        tables=CORPUS_TABLES
    else:tables=MANIFEST_TABLES
    for table in reversed(tables):
        db.execute("DELETE FROM "+_quote(table)+" WHERE owner=?",(owner,))


def _manifest_config(src,dst):
    a=src.execute("SELECT volumes FROM manifest_configuration WHERE singleton=1").fetchone()
    b=dst.execute("SELECT volumes FROM manifest_configuration WHERE singleton=1").fetchone()
    if not a:raise ShardHeld("original manifest volume configuration missing")
    if b and b[0]!=a[0]:raise ShardHeld("manifest volume topology differs")
    if not b:dst.execute("INSERT INTO manifest_configuration VALUES(1,?)",(a[0],))


def _check_fk(db):
    if db.execute("PRAGMA foreign_key_check").fetchone():raise ShardHeld("foreign key check failed")


def migrate(base,plane,scope,destination,*,offline_acknowledged=False):
    _plane(plane)
    owner=owner_key(scope)
    if offline_acknowledged is not True:raise ShardHeld("all writers must be stopped")
    if type(destination) is not int or not 1<=destination<LANES:raise ValueError("destination lane")
    base,_=_private(base)
    with _open(base) as src:
        layout=_layout(src,plane)
        if layout is None:raise ShardHeld("provision topology first")
        target=_target(base,plane,layout,destination)
        src.execute(JOURNAL)
        _initialize(src,plane)
        prior=src.execute("SELECT * FROM dragon_owner_migrations WHERE plane=? AND owner=?",(plane,owner)).fetchone()
        route=src.execute("SELECT lane FROM dragon_shard_routes WHERE plane=? AND owner=?",(plane,owner)).fetchone()
        if prior and (prior["destination"]!=destination or prior["topology_id"]!=layout["id"]):
            raise ShardHeld("migration identity differs")
        if prior and prior["state"]=="complete":
            if route is None or route[0]!=destination:raise ShardHeld("completed route differs")
            return {"state":"complete","replayed":True,"destination":destination,"witness":prior["source_digest"]}
        if route and route[0]!=0:raise ShardHeld("only legacy root owners can be moved")
        src.execute("BEGIN IMMEDIATE")
        try:
            if src.execute("SELECT 1 FROM dragon_owner_migrations WHERE plane=? AND owner<>? AND state='copying'",(plane,owner)).fetchone():
                raise ShardHeld("another migration is incomplete")
            before=_fingerprint(src,owner,plane)
            if not before[1]:raise ShardHeld("legacy owner data missing")
            if prior and prior["source_digest"]!=before[0]:raise ShardHeld("source changed during migration")
            if not prior:src.execute("INSERT INTO dragon_owner_migrations VALUES(?,?,?,?,?,'copying',?,NULL)",
                (plane,owner,destination,layout["id"],before[0],int(time.time())))
            src.execute("COMMIT")
        except BaseException:
            if src.in_transaction:src.execute("ROLLBACK")
            raise
        with _open(target) as dst:
            _initialize(dst,plane)
            src.execute("BEGIN IMMEDIATE")
            try:
                if _fingerprint(src,owner,plane)!=before:raise ShardHeld("source changed")
                dst.execute("BEGIN IMMEDIATE")
                try:
                    existing=_fingerprint(dst,owner,plane)
                    if plane=="manifest":_manifest_config(src,dst)
                    if existing[1]:
                        if existing!=before:raise ShardHeld("destination has conflicting owner data")
                    else:_copy(src,dst,owner,plane)
                    if _fingerprint(dst,owner,plane)!=before:raise ShardHeld("destination witness differs")
                    _check_fk(dst)
                    dst.execute("COMMIT")
                except BaseException:
                    if dst.in_transaction:dst.execute("ROLLBACK")
                    raise
                # Reopen within a fresh target read transaction; a failure
                # leaves the committed copy plus the durable runtime hold.
                dst.execute("BEGIN")
                try:
                    if _fingerprint(dst,owner,plane)!=before:raise ShardHeld("destination readback differs")
                    _remove(src,owner,plane)
                    if _fingerprint(src,owner,plane)[1]:raise ShardHeld("source removal incomplete")
                    _check_fk(src)
                    src.execute("""INSERT INTO dragon_shard_routes VALUES(?,?,?)
                        ON CONFLICT(plane,owner) DO UPDATE SET lane=excluded.lane""",(plane,owner,destination))
                    src.execute("UPDATE dragon_owner_migrations SET state='complete',finished_at=? WHERE plane=? AND owner=?",
                        (int(time.time()),plane,owner))
                    src.execute("COMMIT")
                    dst.execute("COMMIT")
                except BaseException:
                    if dst.in_transaction:dst.execute("ROLLBACK")
                    raise
            except BaseException:
                if src.in_transaction:src.execute("ROLLBACK")
                raise
    return {"state":"complete","replayed":False,"destination":destination,"witness":before[0],
        "rows":before[1],"table_counts":before[2],"physical_erasure":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",required=True)
    parser.add_argument("--plane",choices=("corpus","manifest"),required=True)
    parser.add_argument("--scope-json",required=True)
    parser.add_argument("--destination",type=int,required=True)
    parser.add_argument("--offline-writers-stopped",action="store_true")
    a=parser.parse_args()
    path,_=_private(Path(a.scope_json))
    if path.stat().st_size>4096:raise ShardHeld("scope file bound")
    print(json.dumps(migrate(Path(a.root),a.plane,json.loads(path.read_bytes()),a.destination,
        offline_acknowledged=a.offline_writers_stopped),sort_keys=True))


if __name__=="__main__":main()
