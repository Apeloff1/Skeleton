"""Canonical ten-file Dragon graph, with one local SQLite transaction authority.

Canonical node and evidence rows live ONLY in the attached files. Root retains
a key/URL directory for foreign keys, grants, quotas, and release settlement.
Multi-file commits require rollback journals, not WAL. Stop all old writers
before provisioning. Local storage only; no distributed consensus claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3

from core.dragon_owner_shards import _private,_open,_table,ShardHeld

LANES=10
HEX=re.compile(r"[a-f0-9]{64}\Z")
NODE_COLUMNS=("owner","id","url","host","title","kind","family","first_seen","last_seen","next_review","observations","state")
EDGE_COLUMNS=("owner","id","parent","child","relation","subject","kind","title","witness","snapshot","first_seen","last_seen")
TOPOLOGY="""CREATE TABLE dragon_graph_authority(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),layout TEXT NOT NULL,
 commit_sequence INTEGER NOT NULL CHECK(commit_sequence>=0)
)"""
SCHEMA="""
CREATE TABLE graph_identity(singleton INTEGER PRIMARY KEY CHECK(singleton=1),epoch TEXT NOT NULL,lane INTEGER NOT NULL);
CREATE TABLE nodes(
 owner TEXT NOT NULL,id TEXT NOT NULL,url TEXT NOT NULL,host TEXT NOT NULL,title TEXT NOT NULL,
 kind TEXT NOT NULL,family TEXT NOT NULL,first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL,
 next_review INTEGER NOT NULL,observations INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('candidate','held','retired')),
 PRIMARY KEY(owner,id),UNIQUE(owner,url)
) WITHOUT ROWID;
CREATE INDEX nodes_due ON nodes(owner,state,next_review,id);
CREATE INDEX nodes_family ON nodes(owner,family,id);
CREATE INDEX nodes_host ON nodes(owner,host,id);
CREATE TABLE edges(
 owner TEXT NOT NULL,id TEXT NOT NULL,parent TEXT NOT NULL,child TEXT NOT NULL,relation TEXT NOT NULL,
 subject TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,witness TEXT NOT NULL,snapshot TEXT,
 first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL,PRIMARY KEY(owner,id),
 FOREIGN KEY(owner,child) REFERENCES nodes(owner,id),CHECK(length(witness)=64)
) WITHOUT ROWID;
CREATE INDEX edges_parent ON edges(owner,parent,id);
CREATE INDEX edges_child ON edges(owner,child,id);
CREATE INDEX edges_subject ON edges(owner,subject,id);
CREATE VIRTUAL TABLE graph_search USING fts5(owner,id UNINDEXED,title,url,kind,family,tokenize='unicode61 remove_diacritics 2');
CREATE TABLE graph_probe(id TEXT PRIMARY KEY,payload BLOB NOT NULL,sha256 TEXT NOT NULL CHECK(length(sha256)=64)) WITHOUT ROWID;
"""
PROJECTIONS=("lead_index_changes","lead_index_versions","lead_index_enrollment",
             "lead_edge_dirty","lead_edge_versions","lead_edge_enrollment")
TRIGGERS=("lead_index_insert","lead_index_update","lead_index_delete",
          "lead_edge_partition_insert","lead_edge_partition_update","lead_edge_partition_delete")


class GraphHeld(RuntimeError):
    pass


def lane(identifier):
    if not isinstance(identifier,str) or not HEX.fullmatch(identifier):raise GraphHeld("graph identity invalid")
    return int(identifier[:4],16)*LANES//65536


def _alias(index):
    if type(index) is not int or not 0<=index<LANES:raise GraphHeld("graph lane invalid")
    return "graph"+str(index)


def active(db):
    row=db.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name='dragon_graph_authority'").fetchone()
    if row is None:
        if os.getenv("SKL_DRAGON_CANONICAL_GRAPH_REQUIRED")=="1" or any(_table(db,name) for name in ("lead_node_directory","dragon_graph_direct_writer")):
            raise GraphHeld("canonical graph topology missing")
        return False
    if db.execute("SELECT 1 FROM main.dragon_graph_authority WHERE singleton=1").fetchone() is None:
        raise GraphHeld("canonical graph topology incomplete")
    return True


def _layout(db,root):
    row=db.execute("SELECT layout FROM main.dragon_graph_authority WHERE singleton=1").fetchone()
    try:value=json.loads(row[0])
    except (TypeError,ValueError,IndexError) as exc:raise GraphHeld("graph topology damaged") from exc
    if (not isinstance(value,dict) or set(value)!={"version","epoch","root","paths"} or value["version"]!=1
            or not isinstance(value["epoch"],str) or not HEX.fullmatch(value["epoch"])
            or value["root"]!=str(root) or not isinstance(value["paths"],list) or len(value["paths"])!=LANES
            or any(not isinstance(p,str) or not Path(p).is_absolute() for p in value["paths"])
            or len(set(value["paths"]))!=LANES or str(root) in value["paths"]):
        raise GraphHeld("graph topology binding differs")
    return value


def configure_connection(db):
    """All corpus clients must respect the active graph rollback-journal fence."""
    if active(db):
        if db.execute("PRAGMA main.journal_mode").fetchone()[0].lower()!="delete":
            raise GraphHeld("canonical graph requires root DELETE journal")
        db.execute("PRAGMA main.synchronous=EXTRA")
    else:
        db.execute("PRAGMA main.journal_mode=WAL")
        db.execute("PRAGMA main.synchronous=FULL")


def _attach_files(db,root,layout):
    root,root_identity=_private(root)
    if hasattr(db,"getlimit") and db.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)<LANES:
        raise GraphHeld("SQLite attachment limit below ten")
    if db.in_transaction:raise GraphHeld("attach before transaction")
    if db.execute("PRAGMA main.journal_mode").fetchone()[0].lower()!="delete":
        raise GraphHeld("root journal must be DELETE")
    db.execute("PRAGMA main.synchronous=EXTRA")
    identities={root_identity}
    for index,raw in enumerate(layout["paths"]):
        path,identity=_private(Path(raw))
        if identity in identities:raise GraphHeld("duplicate graph database identity")
        identities.add(identity)
        alias=_alias(index)
        db.execute("ATTACH DATABASE ? AS "+alias,(path.as_uri()+"?mode=rw",))
        if _private(path)[1]!=identity:raise GraphHeld("graph file changed during attach")
        if db.execute("PRAGMA "+alias+".journal_mode").fetchone()[0].lower()!="delete":
            raise GraphHeld("graph shard journal must be DELETE")
        db.execute("PRAGMA "+alias+".synchronous=EXTRA")
        marker=db.execute("SELECT epoch,lane FROM "+alias+".graph_identity WHERE singleton=1").fetchone()
        if marker is None or tuple(marker)!=(layout["epoch"],index):
            raise GraphHeld("graph shard identity differs")
    if _private(root)[1]!=root_identity:raise GraphHeld("graph root changed during attach")


def attach(db,root):
    root=Path(root)
    if not active(db):return False
    if (not _table(db,"lead_node_directory") or _table(db,"lead_nodes") or _table(db,"lead_edges") or _table(db,"lead_fts")):
        raise GraphHeld("legacy graph tables present or directory unavailable")
    layout=_layout(db,root)
    _attach_files(db,root,layout)
    for view,table,columns in (("lead_nodes","nodes",NODE_COLUMNS),("lead_edges","edges",EDGE_COLUMNS)):
        db.execute("CREATE TEMP VIEW "+view+" AS "+" UNION ALL ".join(
            "SELECT "+",".join(columns)+" FROM "+_alias(i)+"."+table for i in range(LANES)))
    return True


def tables(db,identifier):
    if not active(db):return "main.lead_nodes","main.lead_edges","main.lead_fts"
    alias=_alias(lane(identifier))
    return alias+".nodes",alias+".edges",alias+".graph_search"


def _fence(db):
    if not db.in_transaction:raise GraphHeld("canonical graph write requires transaction")
    if active(db):
        if db.execute("UPDATE main.dragon_graph_authority SET commit_sequence=commit_sequence+1 WHERE singleton=1").rowcount!=1:
            raise GraphHeld("root commit fence missing")


def read_fence(db):
    if not db.in_transaction:raise GraphHeld("canonical graph read requires transaction")
    if db.execute("SELECT commit_sequence FROM main.dragon_graph_authority WHERE singleton=1").fetchone() is None:
        raise GraphHeld("root read fence missing")
    # Pin each rollback-journal read lock before reading graph rows. Independent
    # local review writers cannot commit on an already-pinned lane.
    for i in range(LANES):
        if db.execute("SELECT 1 FROM "+_alias(i)+".graph_identity WHERE singleton=1").fetchone() is None:
            raise GraphHeld("graph lane read fence missing")


def insert_node(db,args):
    owner,identifier,url,host,title,kind,family,first,last,due=args
    node,_,fts=tables(db,identifier)
    _fence(db)
    if active(db):
        # Same key and canonical URL enforce cross-lane uniqueness and root
        # FKs. Remaining columns deliberately contain no graph authority.
        db.execute("""INSERT INTO main.lead_node_directory VALUES(?,?,?,'','','','',0,0,0,0,'candidate')""",
                   (owner,identifier,url))
    db.execute("INSERT INTO "+node+" VALUES(?,?,?,?,?,?,?,?,?,?,0,'candidate')",args)
    db.execute("INSERT INTO "+fts+"(owner,id,title,url,kind,family) VALUES(?,?,?,?,?,?)",
               (owner,identifier,title,url,kind,family))


def insert_edge(db,args):
    _,edge,_=tables(db,args[3])
    _fence(db)
    db.execute("INSERT INTO "+edge+" VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",args)


def touch_edge(db,owner,identifier,child,now):
    _,edge,_=tables(db,child)
    _fence(db)
    if db.execute("UPDATE "+edge+" SET last_seen=MAX(last_seen,?) WHERE owner=? AND id=?",(now,owner,identifier)).rowcount!=1:
        raise GraphHeld("edge update identity missing")


def touch_node(db,owner,identifier,now,*,observation=False):
    node,_,_=tables(db,identifier)
    _fence(db)
    prefix="observations=observations+1," if observation else ""
    if db.execute("UPDATE "+node+" SET "+prefix+"last_seen=MAX(last_seen,?) WHERE owner=? AND id=?",(now,owner,identifier)).rowcount!=1:
        raise GraphHeld("node update identity missing")


def review_node(db,owner,identifier,state,due):
    node,_,_=tables(db,identifier)
    _fence(db)
    return db.execute("UPDATE "+node+" SET state=?,next_review=? WHERE owner=? AND id=?",(state,due,owner,identifier))


def page(db,owner,terms,*,state,family,host,lower,cutoff,limit):
    import time
    read_fence(db)
    deadline=time.monotonic()+3
    rows=[]
    db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    try:
        for i in range(LANES):
            if time.monotonic()>deadline:raise GraphHeld("canonical graph query deadline")
            alias=_alias(i)
            sql="SELECT n.* FROM "+alias+".nodes n"
            values=[owner,state,lower];where=["n.owner=?","n.state=?","n.id>?"]
            if terms:
                sql="SELECT n.* FROM "+alias+".graph_search f CROSS JOIN "+alias+".nodes n ON f.owner=n.owner AND f.id=n.id"
                where.append("graph_search MATCH ?")
                values.append('owner:"'+owner+'" AND '+' AND '.join('"'+term+'"' for term in terms))
            if family:where.append("n.family=?");values.append(family)
            if host:where.append("n.host=?");values.append(host)
            if cutoff is not None:where.append("n.next_review<=?");values.append(cutoff)
            rows.extend(db.execute(sql+" WHERE "+" AND ".join(where)+" ORDER BY n.id LIMIT ?",[*values,limit+1]).fetchall())
        if len({r["id"] for r in rows})!=len(rows):raise GraphHeld("duplicate canonical node")
        return sorted(rows,key=lambda r:r["id"])[:limit+1]
    finally:db.set_progress_handler(None,0)


def _fingerprint(rows):
    h=hashlib.sha256();count=0
    for row in rows:
        raw=json.dumps(tuple(row),ensure_ascii=True,separators=(",",":"),allow_nan=False).encode()
        h.update(len(raw).to_bytes(8,"big"));h.update(raw);count+=1
    return count,h.hexdigest()


def _iter(db,sql,args=()):
    cursor=db.execute(sql,args)
    while batch:=cursor.fetchmany(256):
        yield from batch


def _verify_graph(db):
    from core.dragon_lead_graph import lead_id
    from core.dragon_game_corpus import digest
    for index in range(LANES):
        alias=_alias(index)
        if db.execute("PRAGMA "+alias+".foreign_key_check").fetchone():raise GraphHeld("graph foreign key check failed")
        for table,field in (("nodes","id"),("edges","child")):
            for row in _iter(db,"SELECT owner,"+field+" FROM "+alias+"."+table):
                if lane(row[1])!=index or not HEX.fullmatch(row[0]):raise GraphHeld("graph row outside partition")
        for row in _iter(db,"SELECT id,url FROM "+alias+".nodes"):
            if lead_id(row["url"])!=row["id"]:raise GraphHeld("canonical node ID witness differs")
        for row in _iter(db,"SELECT id,parent,child,relation,subject,kind,title,witness,snapshot FROM "+alias+".edges"):
            if digest([row[k] for k in ("parent","child","relation","subject","kind","title","witness","snapshot")])!=row["id"]:
                raise GraphHeld("canonical edge ID witness differs")
        n=db.execute("SELECT COUNT(*) FROM "+alias+".nodes").fetchone()[0]
        ft=db.execute("SELECT COUNT(*) FROM "+alias+".graph_search").fetchone()[0]
        if n!=ft:raise GraphHeld("graph FTS row count differs")
        # Scan the FTS rows once, using the canonical node primary key rather
        # than an unindexed FTS ID lookup for every canonical node.
        bad=db.execute("SELECT 1 FROM "+alias+".graph_search f LEFT JOIN "+alias+".nodes n ON n.owner=f.owner AND n.id=f.id AND n.title=f.title AND n.url=f.url AND n.kind=f.kind AND n.family=f.family WHERE n.id IS NULL LIMIT 1").fetchone()
        duplicate=db.execute("SELECT 1 FROM "+alias+".graph_search GROUP BY owner,id HAVING COUNT(*)<>1 LIMIT 1").fetchone()
        if bad or duplicate:raise GraphHeld("graph FTS witness differs")


def _union(table,columns):
    return " UNION ALL ".join("SELECT "+",".join(columns)+" FROM "+_alias(i)+"."+table for i in range(LANES))


def _verify_directory(db):
    union=_union("nodes",("owner","id","url"))
    if _fingerprint(_iter(db,"SELECT owner,id,url FROM main.lead_node_directory ORDER BY owner,id"))!=_fingerprint(_iter(db,"SELECT * FROM ("+union+") ORDER BY owner,id")):
        raise GraphHeld("root node directory differs")
    for index in range(LANES):
        alias=_alias(index)
        if db.execute("SELECT 1 FROM "+alias+".edges e WHERE e.parent<>? AND NOT EXISTS(SELECT 1 FROM main.lead_node_directory d WHERE d.owner=e.owner AND d.id=e.parent) LIMIT 1",("0"*64,)).fetchone():
            raise GraphHeld("cross-shard edge parent missing")
        if db.execute("SELECT 1 FROM "+alias+".edges e WHERE e.snapshot IS NOT NULL AND NOT EXISTS(SELECT 1 FROM main.lead_snapshots s WHERE s.owner=e.owner AND s.id=e.snapshot) LIMIT 1").fetchone():
            raise GraphHeld("edge snapshot missing")
    if db.execute("PRAGMA main.foreign_key_check").fetchone():raise GraphHeld("root foreign key check failed")
    # Quotas and observation identities remain authoritative on the root.
    for kind,table,field in (("nodes","nodes","id"),("edges","edges","child")):
        grouped=" UNION ALL ".join("SELECT owner,COUNT(*) AS n FROM "+_alias(i)+"."+table+" GROUP BY owner" for i in range(LANES))
        actual="SELECT owner,SUM(n) AS n FROM ("+grouped+") GROUP BY owner"
        if db.execute("WITH totals AS ("+actual+") SELECT 1 FROM main.lead_owner o LEFT JOIN totals t ON t.owner=o.owner WHERE o."+kind+"<>COALESCE(t.n,0) LIMIT 1").fetchone():
            raise GraphHeld("graph owner counters differ")
        if db.execute("WITH totals AS ("+actual+") SELECT 1 FROM totals t LEFT JOIN main.lead_owner o ON o.owner=t.owner WHERE o.owner IS NULL LIMIT 1").fetchone():
            raise GraphHeld("graph owner missing")
        for i in range(LANES):
            sql="SELECT 1 FROM main.lead_lane_counts c LEFT JOIN (SELECT owner,COUNT(*) AS n FROM "+_alias(i)+"."+table+" GROUP BY owner) t ON t.owner=c.owner WHERE c.lane=? AND c."+kind+"<>COALESCE(t.n,0) LIMIT 1"
            if db.execute(sql,(i,)).fetchone():raise GraphHeld("graph lane counters differ")


def provision(root,paths,*,offline_acknowledged=False):
    """Offline atomic relocation of the entire graph of one corpus root.

    A failed commit never activates the topology. Unpublished child files
    must be inspected by the operator before another attempt.
    """
    if offline_acknowledged is not True:raise GraphHeld("stop all writers before graph provisioning")
    from core.dragon_owner_shards import guard_root
    from core.dragon_lead_graph import LeadGraph
    root,_=_private(Path(root));guard_root(root,"corpus")
    paths=tuple(Path(p) for p in paths)
    if len(paths)!=LANES or len(set(paths))!=LANES or root in paths:
        raise ValueError("exactly ten distinct absolute unused shard paths")
    if os.getenv("SKL_DRAGON_CANONICAL_GRAPH_REQUIRED")=="1":
        raise GraphHeld("leave required flag unset during initial offline provisioning")
    # Initialize the unsharded schema before changing journal mode.
    with LeadGraph(root)._db() as db:
        if active(db):raise GraphHeld("canonical graph already provisioned")
    with _open(root) as db:
        if active(db):raise GraphHeld("canonical graph already provisioned")
        for p in paths:
            if not p.is_absolute() or any(x.is_symlink() for x in (p,*p.parents)) or p.exists() or any(
                    Path(str(p)+suffix).exists() or Path(str(p)+suffix).is_symlink() for suffix in ("-wal","-shm","-journal")):
                raise GraphHeld("graph shard paths must be unused and canonical")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA legacy_alter_table=OFF")
        if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]!=0:
            raise GraphHeld("root WAL checkpoint busy")
        if db.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower()!="delete":
            raise GraphHeld("root journal conversion failed")
        db.execute("PRAGMA synchronous=EXTRA")
        epoch=secrets.token_hex(32)
        layout={"version":1,"epoch":epoch,"root":str(root),"paths":[str(p) for p in paths]}
        for i,p in enumerate(paths):
            _private(p,create=True)
            with _open(p) as child:
                child.execute("PRAGMA journal_mode=DELETE")
                child.execute("PRAGMA synchronous=EXTRA")
                from core.dragon_graph_direct_writer import SCHEMA as DIRECT_SCHEMA
                child.executescript(SCHEMA+DIRECT_SCHEMA)
                child.execute("INSERT INTO graph_identity VALUES(1,?,?)",(epoch,i))
        _attach_files(db,root,layout)
        db.execute("BEGIN IMMEDIATE")
        try:
            if db.execute("PRAGMA main.foreign_key_check").fetchone():raise GraphHeld("legacy graph foreign keys fail")
            nodes=_fingerprint(_iter(db,"SELECT * FROM main.lead_nodes ORDER BY owner,id"))
            edges=_fingerprint(_iter(db,"SELECT * FROM main.lead_edges ORDER BY owner,id"))
            for row in _iter(db,"SELECT * FROM main.lead_nodes ORDER BY owner,id"):
                alias=_alias(lane(row["id"]))
                db.execute("INSERT INTO "+alias+".nodes VALUES("+",".join("?" for _ in NODE_COLUMNS)+")",tuple(row))
                db.execute("INSERT INTO "+alias+".graph_search VALUES(?,?,?,?,?,?)",
                    tuple(row[k] for k in ("owner","id","title","url","kind","family")))
            for row in _iter(db,"SELECT * FROM main.lead_edges ORDER BY owner,id"):
                alias=_alias(lane(row["child"]))
                db.execute("INSERT INTO "+alias+".edges VALUES("+",".join("?" for _ in EDGE_COLUMNS)+")",tuple(row))
            if nodes!=_fingerprint(_iter(db,"SELECT * FROM ("+_union("nodes",NODE_COLUMNS)+") ORDER BY owner,id")):
                raise GraphHeld("node migration fingerprint differs")
            if edges!=_fingerprint(_iter(db,"SELECT * FROM ("+_union("edges",EDGE_COLUMNS)+") ORDER BY owner,id")):
                raise GraphHeld("edge migration fingerprint differs")
            _verify_graph(db)
            for trigger in TRIGGERS:db.execute("DROP TRIGGER IF EXISTS main."+trigger)
            for table in PROJECTIONS:
                if _table(db,table):db.execute("DELETE FROM main."+table)
            db.execute("DROP TABLE main.lead_edges")
            db.execute("DROP TABLE main.lead_fts")
            db.execute("ALTER TABLE main.lead_nodes RENAME TO lead_node_directory")
            for name in ("lead_nodes_due","lead_nodes_family","lead_nodes_host"):db.execute("DROP INDEX IF EXISTS main."+name)
            db.execute("""UPDATE main.lead_node_directory SET host='',title='',kind='',family='',
                first_seen=0,last_seen=0,next_review=0,observations=0,state='candidate'""")
            _verify_directory(db)
            db.execute(TOPOLOGY)
            db.execute("CREATE TABLE dragon_graph_probe(id TEXT PRIMARY KEY,witness TEXT NOT NULL) WITHOUT ROWID")
            db.execute("INSERT INTO main.dragon_graph_authority VALUES(1,?,0)",(json.dumps(layout,separators=(",",":")),))
            from core.dragon_graph_direct_writer import publish_marker
            publish_marker(db,epoch)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"state":"active","epoch":epoch,"physical_lanes":LANES,"nodes":nodes[0],"node_sha256":nodes[1],
        "edges":edges[0],"edge_sha256":edges[1],"coordinated_writer":True,"capacity_verified":False}


def qualify(root,*,full=False):
    """Report actual configured file identity and optional full integrity audit."""
    root,_=_private(Path(root))
    with _open(root) as db:
        if not active(db):raise GraphHeld("canonical graph not provisioned")
        db.execute("PRAGMA foreign_keys=ON")
        layout=_layout(db,root);attach(db,root)
        db.execute("BEGIN")
        try:
            read_fence(db)
            result=[]
            for i,raw in enumerate(layout["paths"]):
                alias=_alias(i);path=Path(raw);st=path.stat()
                if full and db.execute("PRAGMA "+alias+".integrity_check").fetchone()[0]!="ok":
                    raise GraphHeld("shard integrity check failed")
                result.append({"lane":i,"device":st.st_dev,"file_bytes":st.st_size,
                    "free_bytes":shutil.disk_usage(path.parent).free,
                    "nodes":db.execute("SELECT COUNT(*) FROM "+alias+".nodes").fetchone()[0] if full else None,
                    "edges":db.execute("SELECT COUNT(*) FROM "+alias+".edges").fetchone()[0] if full else None})
            if full:
                if db.execute("PRAGMA main.integrity_check").fetchone()[0]!="ok":raise GraphHeld("root integrity check failed")
                _verify_graph(db);_verify_directory(db)
                from core.dragon_graph_direct_writer import verify
                verify(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"epoch":layout["epoch"],"lanes":result,"full_integrity_audit":full,
        "capacity_verified":False,"power_loss_qualified":False,"coordinated_writer":True}



def _probe_connection(root):
    """Yield an attached connection; callers close it via the context manager."""
    from contextlib import contextmanager
    @contextmanager
    def connect():
        with _open(Path(root)) as db:
            if not active(db):raise GraphHeld("canonical graph not provisioned")
            db.execute("PRAGMA foreign_keys=ON")
            attach(db,Path(root))
            yield db
    return connect()


def _verify_probe(db,identifier):
    row=db.execute("SELECT witness FROM main.dragon_graph_probe WHERE id=?",(identifier,)).fetchone()
    if row is None:raise GraphHeld("probe root receipt missing")
    try:expected=json.loads(row[0])
    except (TypeError,ValueError) as exc:raise GraphHeld("probe root receipt invalid") from exc
    if not isinstance(expected,list) or len(expected)!=LANES:
        raise GraphHeld("probe witness count")
    for i,item in enumerate(expected):
        if (not isinstance(item,dict) or set(item)!={"bytes","sha256"} or type(item["bytes"]) is not int
                or not 4096<=item["bytes"]<=16*1024**2 or not isinstance(item["sha256"],str) or not HEX.fullmatch(item["sha256"])):
            raise GraphHeld("probe witness invalid")
        row=db.execute("SELECT payload,sha256 FROM "+_alias(i)+".graph_probe WHERE id=?",(identifier,)).fetchone()
        if row is None or len(row[0])!=item["bytes"] or row[1]!=item["sha256"] or hashlib.sha256(row[0]).hexdigest()!=row[1]:
            raise GraphHeld("physical probe bytes differ")
    return expected


def recover_probe(root,identifier):
    """Reopen, verify all committed canary bytes, remove only this probe.

    A mismatch is a custody hold, never an instruction to erase graph data.
    """
    if not isinstance(identifier,str) or not HEX.fullmatch(identifier):raise ValueError("probe identity")
    with _probe_connection(root) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            expected=_verify_probe(db,identifier)
            for i in range(LANES):
                if db.execute("DELETE FROM "+_alias(i)+".graph_probe WHERE id=?",(identifier,)).rowcount!=1:
                    raise GraphHeld("probe cleanup identity differs")
            if db.execute("DELETE FROM main.dragon_graph_probe WHERE id=?",(identifier,)).rowcount!=1:
                raise GraphHeld("probe root cleanup identity differs")
            _fence(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    with _probe_connection(root) as db:
        db.execute("BEGIN")
        try:
            read_fence(db)
            if db.execute("SELECT 1 FROM main.dragon_graph_probe WHERE id=?",(identifier,)).fetchone() or any(
                db.execute("SELECT 1 FROM "+_alias(i)+".graph_probe WHERE id=?",(identifier,)).fetchone() for i in range(LANES)):
                raise GraphHeld("probe cleanup not durable")
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"probe_id":identifier,"verified_bytes":sum(item["bytes"] for item in expected),
            "lane_receipts":expected,"readback_verified":True,"cleanup_verified":True,
            "capacity_verified":False,"power_loss_qualified":False}


def write_probe(root,*,bytes_per_lane=1024**2,acknowledged=False):
    """Actual bounded local-device write/read/delete, not a capacity benchmark."""
    if acknowledged is not True:raise GraphHeld("explicit physical write acknowledgement")
    if type(bytes_per_lane) is not int or not 4096<=bytes_per_lane<=16*1024**2:
        raise ValueError("probe bytes per lane")
    identifier=secrets.token_hex(32)
    with _probe_connection(root) as db:
        layout=_layout(db,Path(root))
        # Devices may overlap. Reserve conservatively per actual filesystem,
        # not per advertised logical shard; never assume separate capacity.
        devices={}
        for path in [Path(root),*(Path(x) for x in layout["paths"])]:
            dev=path.stat().st_dev
            count,folder=devices.get(dev,(0,path.parent))
            devices[dev]=(count+1,folder)
        for count,folder in devices.values():
            if shutil.disk_usage(folder).free<512*1024**2+count*bytes_per_lane*4:
                raise GraphHeld("physical probe free-space floor")
        db.execute("BEGIN IMMEDIATE")
        try:
            if db.execute("SELECT 1 FROM main.dragon_graph_probe LIMIT 1").fetchone():
                raise GraphHeld("previous probe requires explicit recovery")
            expected=[]
            for i in range(LANES):
                raw=os.urandom(bytes_per_lane);checksum=hashlib.sha256(raw).hexdigest()
                db.execute("INSERT INTO "+_alias(i)+".graph_probe VALUES(?,?,?)",(identifier,raw,checksum))
                expected.append({"bytes":len(raw),"sha256":checksum})
            db.execute("INSERT INTO main.dragon_graph_probe VALUES(?,?)",(identifier,json.dumps(expected,separators=(",",":"))))
            _fence(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return recover_probe(root,identifier)


def pending_probes(root):
    with _probe_connection(root) as db:
        rows=db.execute("SELECT id FROM main.dragon_graph_probe ORDER BY id LIMIT 32").fetchall()
    return {"pending_probe_ids":[r[0] for r in rows],"bounded":True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    create=sub.add_parser("provision");create.add_argument("--root",required=True)
    create.add_argument("--offline-writers-stopped",action="store_true");create.add_argument("paths",nargs=LANES)
    audit=sub.add_parser("qualify");audit.add_argument("--root",required=True);audit.add_argument("--full",action="store_true")
    write=sub.add_parser("probe");write.add_argument("--root",required=True)
    write.add_argument("--bytes-per-lane",type=int,default=1024**2);write.add_argument("--acknowledge-device-writes",action="store_true")
    pending=sub.add_parser("pending-probes");pending.add_argument("--root",required=True)
    recovery=sub.add_parser("recover-probe");recovery.add_argument("--root",required=True);recovery.add_argument("--id",required=True)
    upgrade=sub.add_parser("enable-direct-writers");upgrade.add_argument("--root",required=True)
    upgrade.add_argument("--offline-writers-stopped",action="store_true")
    a=parser.parse_args()
    if a.command=="enable-direct-writers":
        from core.dragon_graph_direct_writer import install
        receipt=install(a.root,offline_acknowledged=a.offline_writers_stopped)
    elif a.command=="provision":receipt=provision(a.root,a.paths,offline_acknowledged=a.offline_writers_stopped)
    elif a.command=="qualify":receipt=qualify(a.root,full=a.full)
    elif a.command=="probe":receipt=write_probe(a.root,bytes_per_lane=a.bytes_per_lane,acknowledged=a.acknowledge_device_writes)
    elif a.command=="pending-probes":receipt=pending_probes(a.root)
    else:receipt=recover_probe(a.root,a.id)
    print(json.dumps(receipt,sort_keys=True))


if __name__=="__main__":main()
