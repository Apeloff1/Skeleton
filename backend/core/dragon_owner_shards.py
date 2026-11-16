"""Physical owner partitions with persistent, fail-closed routing.

Provision only during an operator-controlled offline maintenance window.
No automatic migration, fallback, deletion, network or source authority.
The root database is the routing authority and the original lane.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from core.dragon_hoarder_bulk import owner_key

LANES=10
PLANES={"corpus","manifest"}
KEY=re.compile(r"[a-f0-9]{64}\Z")
SCHEMA="""
CREATE TABLE IF NOT EXISTS dragon_shard_topology(
 plane TEXT PRIMARY KEY, layout TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS dragon_shard_routes(
 plane TEXT NOT NULL, owner TEXT NOT NULL, lane INTEGER NOT NULL CHECK(lane>=0 AND lane<10),
 PRIMARY KEY(plane,owner)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS dragon_shard_cursor(
 plane TEXT NOT NULL, job TEXT NOT NULL, lane INTEGER NOT NULL CHECK(lane>=0 AND lane<10),
 PRIMARY KEY(plane,job)
) WITHOUT ROWID;
"""
MARKER="""CREATE TABLE IF NOT EXISTS dragon_shard_identity(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), plane TEXT NOT NULL, lane INTEGER NOT NULL,
 topology_id TEXT NOT NULL
)"""


class ShardHeld(RuntimeError):
    """The configured shard topology cannot safely serve a request."""


def _private(path,*,create=False):
    p=Path(path)
    if not p.is_absolute() or any(x.is_symlink() for x in (p,*p.parents)):
        raise ShardHeld("canonical shard path required")
    parent=p.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or os.name=="posix" and (parent.st_uid!=os.getuid() or parent.st_mode&0o077):
        raise ShardHeld("private shard directory required")
    if create:
        fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
        os.close(fd)
    s=p.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or os.name=="posix" and (s.st_uid!=os.getuid() or s.st_mode&0o077):
        raise ShardHeld("private single-link shard file required")
    for suffix in ("-wal","-shm","-journal"):
        side=Path(str(p)+suffix)
        if side.is_symlink():raise ShardHeld("unsafe shard sidecar")
        if side.exists():
            info=side.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or os.name=="posix" and (
                    info.st_uid!=os.getuid() or info.st_mode&0o077):
                raise ShardHeld("unsafe shard sidecar")
    return p,(s.st_dev,s.st_ino)


@contextmanager
def _open(path):
    p,before=_private(path)
    db=sqlite3.connect(p.as_uri()+"?mode=rw",uri=True,timeout=5,isolation_level=None)
    db.row_factory=sqlite3.Row
    try:
        if _private(p)[1]!=before:raise ShardHeld("shard replaced during open")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA synchronous=FULL")
        yield db
    finally:db.close()


def _plane(plane):
    if plane not in PLANES:raise ValueError("unknown shard plane")
    return plane


def _table(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None


def _migration_guard(db,plane):
    if _table(db,"dragon_owner_migrations") and db.execute(
            "SELECT 1 FROM dragon_owner_migrations WHERE plane=? AND state='copying' LIMIT 1",(plane,)).fetchone():
        raise ShardHeld("offline owner migration incomplete")


def guard_root(base,plane):
    _plane(plane)
    with _open(base) as db:
        _migration_guard(db,plane)


def _required(plane):
    return os.getenv("SKL_DRAGON_"+plane.upper()+"_SHARDS_REQUIRED","")=="1"


def _layout(db,plane):
    if not _table(db,"dragon_shard_topology"):return None
    r=db.execute("SELECT layout FROM dragon_shard_topology WHERE plane=?",(plane,)).fetchone()
    if not r:return None
    value=json.loads(r["layout"])
    if not isinstance(value,dict) or set(value)!={"id","paths"} or not isinstance(value["id"],str) or not KEY.fullmatch(value["id"]) or (
            not isinstance(value["paths"],list) or len(value["paths"])!=LANES or
            any(not isinstance(p,str) or not Path(p).is_absolute() for p in value["paths"]) or
            len(set(value["paths"]))!=LANES):
        raise ShardHeld("invalid shard layout")
    return value


def _target(base,plane,layout,lane):
    if type(lane) is not int or not 0<=lane<LANES or Path(layout["paths"][0])!=base:
        raise ShardHeld("shard root binding differs")
    p,_=_private(layout["paths"][lane])
    with _open(p) as db:
        if not _table(db,"dragon_shard_identity"):raise ShardHeld("shard identity missing")
        row=db.execute("SELECT plane,lane,topology_id FROM dragon_shard_identity WHERE singleton=1").fetchone()
        if row is None or tuple(row)!=(plane,lane,layout["id"]):
            raise ShardHeld("shard identity differs")
    return p


def provision(base,plane,paths,*,offline_acknowledged=False):
    """Create nine new files, then atomically publish all routes' topology.

    A partially provisioned topology is never activated. On interruption,
    inspect and remove only verified empty/unpublished staging files manually.
    The existing root is never renamed, overwritten or copied.
    """
    import secrets
    _plane(plane)
    if offline_acknowledged is not True:raise ShardHeld("offline writer stop required")
    base,_=_private(base)
    paths=tuple(Path(p) for p in paths)
    if len(paths)!=LANES or paths[0]!=base or len(set(paths))!=LANES:
        raise ValueError("exactly ten distinct paths starting with root required")
    with _open(base) as db:
        db.executescript(SCHEMA)
        if _layout(db,plane) is not None or _table(db,"dragon_shard_identity"):
            raise ShardHeld("topology already provisioned")
        for path in paths[1:]:
            if path.exists() or path.is_symlink() or any(Path(str(path)+x).exists() or Path(str(path)+x).is_symlink() for x in ("-wal","-shm","-journal")):
                raise ShardHeld("new shard paths must be unused")
        layout={"id":secrets.token_hex(32),"paths":[str(p) for p in paths]}
        db.execute("BEGIN IMMEDIATE")
        try:
            for lane,p in enumerate(paths[1:],1):
                _private(p,create=True)
                with _open(p) as child:
                    child.execute(MARKER)
                    child.execute("INSERT INTO dragon_shard_identity VALUES(1,?,?,?)",(plane,lane,layout["id"]))
            db.execute(MARKER)
            db.execute("INSERT INTO dragon_shard_identity VALUES(1,?,?,?)",(plane,0,layout["id"]))
            db.execute("INSERT INTO dragon_shard_topology VALUES(?,?)",(plane,json.dumps(layout,separators=(",",":"))))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"plane":plane,"shards":LANES,"physical_files":True,"existing_owners_migrated":False}


def _legacy_owner(db,owner):
    # Canonical ordinary tables with a leading owner key. Virtual FTS shadows
    # are excluded; their rows are subordinate to canonical owner records.
    for row in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        name=row["name"]
        if name.startswith("dragon_shard_") or name in {"world_subscriptions","world_origin_guard"} or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",name):
            continue
        if not row["sql"] or "CREATE VIRTUAL TABLE" in row["sql"].upper():continue
        cols=db.execute('PRAGMA table_info("'+name+'")').fetchall()
        if not any(c["name"]=="owner" for c in cols):continue
        if db.execute('SELECT 1 FROM "'+name+'" WHERE owner=? LIMIT 1',(owner,)).fetchone():
            return True
    return False


def owner_path(base,plane,scope):
    """Existing owners stay in lane zero, new owners receive a durable lane."""
    _plane(plane)
    key=owner_key(scope)
    base,_=_private(base)
    with _open(base) as db:
        _migration_guard(db,plane)
        layout=_layout(db,plane)
        if layout is None:
            if _required(plane) or _table(db,"dragon_shard_identity"):raise ShardHeld("missing root topology")
            return base
        # Validate root marker without a second connection.
        if not _table(db,"dragon_shard_identity"):raise ShardHeld("root marker missing")
        marker=db.execute("SELECT plane,lane,topology_id FROM dragon_shard_identity WHERE singleton=1").fetchone()
        if marker is None or tuple(marker)!=(plane,0,layout["id"]):raise ShardHeld("root marker differs")
        row=db.execute("SELECT lane FROM dragon_shard_routes WHERE plane=? AND owner=?",(plane,key)).fetchone()
        if row is not None:
            lane=row["lane"]
        else:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT lane FROM dragon_shard_routes WHERE plane=? AND owner=?",(plane,key)).fetchone()
                lane=row["lane"] if row is not None else (0 if _legacy_owner(db,key) else int(key[:16],16)%LANES)
                if row is None:
                    if lane:_target(base,plane,layout,lane)
                    db.execute("INSERT INTO dragon_shard_routes VALUES(?,?,?)",(plane,key,lane))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
    return _target(base,plane,layout,lane)


def shard_paths(base,plane):
    _plane(plane)
    base,_=_private(base)
    with _open(base) as db:
        _migration_guard(db,plane)
        layout=_layout(db,plane)
        if layout is None:
            if _required(plane) or _table(db,"dragon_shard_identity"):raise ShardHeld("missing root topology")
            return (base,)
    return tuple(_target(base,plane,layout,i) for i in range(LANES))


def next_path(base,plane,job):
    """Durable per-job rotation; a held shard does not block the next pulse."""
    _plane(plane)
    if not isinstance(job,str) or not re.fullmatch(r"[a-z_]{1,64}",job):raise ValueError("job identity")
    base,_=_private(base)
    with _open(base) as db:
        _migration_guard(db,plane)
        layout=_layout(db,plane)
        if layout is None:
            if _required(plane) or _table(db,"dragon_shard_identity"):raise ShardHeld("missing root topology")
            return base
        db.execute("BEGIN IMMEDIATE")
        try:
            row=db.execute("SELECT lane FROM dragon_shard_cursor WHERE plane=? AND job=?",(plane,job)).fetchone()
            lane=row["lane"] if row else 0
            db.execute("""INSERT INTO dragon_shard_cursor VALUES(?,?,?)
                ON CONFLICT(plane,job) DO UPDATE SET lane=excluded.lane""",(plane,job,(lane+1)%LANES))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return _target(base,plane,layout,lane)


def next_paths(base,plane,job,*,count=2):
    """Reserve a bounded set of distinct owner roots with one durable cursor.

    Missing children are reported individually, not silently replaced by the
    root. Cursor advancement commits before any child validation.
    """
    _plane(plane)
    if type(count) is not int or not 1<=count<=LANES:raise ValueError("maintenance lane count")
    if not isinstance(job,str) or not re.fullmatch(r"[a-z_]{1,64}",job):raise ValueError("job identity")
    base,_=_private(base)
    with _open(base) as db:
        _migration_guard(db,plane)
        layout=_layout(db,plane)
        if layout is None:
            if _required(plane) or _table(db,"dragon_shard_identity"):raise ShardHeld("missing root topology")
            return ((0,base),),()
        db.execute("BEGIN IMMEDIATE")
        try:
            row=db.execute("SELECT lane FROM dragon_shard_cursor WHERE plane=? AND job=?",(plane,job)).fetchone()
            start=row["lane"] if row else 0
            if type(start) is not int or not 0<=start<LANES:raise ShardHeld("maintenance cursor invalid")
            lanes=tuple((start+i)%LANES for i in range(count))
            db.execute("""INSERT INTO dragon_shard_cursor VALUES(?,?,?)
                ON CONFLICT(plane,job) DO UPDATE SET lane=excluded.lane""",(plane,job,(start+count)%LANES))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    ready=[];held=[];identities=set()
    for lane in lanes:
        try:
            path=_target(base,plane,layout,lane)
            identity=_private(path)[1]
            if identity in identities:raise ShardHeld("maintenance roots alias")
            identities.add(identity)
            ready.append((lane,path))
        except (ShardHeld,OSError,sqlite3.Error):
            held.append(lane)
    return tuple(ready),tuple(held)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plane",choices=sorted(PLANES),required=True)
    parser.add_argument("--offline-writers-stopped",action="store_true")
    parser.add_argument("paths",nargs=LANES)
    args=parser.parse_args()
    print(json.dumps(provision(args.paths[0],args.plane,args.paths,
        offline_acknowledged=args.offline_writers_stopped)))


if __name__=="__main__":main()
