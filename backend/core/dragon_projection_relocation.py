"""Resumable, epoch-fenced migration of derived physical graph projections.

Canonical graph rows and grants never move here. Old projection directories
are retained, while a new destination receives fresh generation identities.
Canonical search/traversal stays available while indexes rebuild. Explicit
offline staging prevents different processes from binding different roots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import time

from core.dragon_graph_deployment import _ack,_dir,DeploymentHeld
from core.dragon_owner_shards import _open,_table
from core.dragon_hoarder_bulk import owner_key
from core.dragon_lead_index_shards import LANES,HEX,bounds

KINDS={
    "nodes":("lead_index_enrollment","lead_index_versions","lead_index_changes","SKL_DRAGON_LEAD_INDEX_ROOT"),
    "edges":("lead_edge_enrollment","lead_edge_versions","lead_edge_dirty","SKL_DRAGON_LEAD_EDGE_ROOT"),
}
SCHEMA="""CREATE TABLE IF NOT EXISTS dragon_projection_relocation(
 kind TEXT PRIMARY KEY CHECK(kind IN ('nodes','edges')),
 operation TEXT NOT NULL,target TEXT NOT NULL,device INTEGER NOT NULL,inode INTEGER NOT NULL,
 cursor TEXT NOT NULL,owners INTEGER NOT NULL CHECK(owners>=0),
 phase TEXT NOT NULL CHECK(phase IN ('resetting','rebuilding'))
) WITHOUT ROWID"""
LIMIT=32


def _kind(kind):
    if kind not in KINDS:raise ValueError("projection kind")
    return KINDS[kind]


def _target(kind):
    raw=os.getenv(_kind(kind)[3],"").strip()
    if not raw:raise DeploymentHeld("projection root unconfigured")
    return _dir(Path(raw))


def _row(db,kind):
    if not _table(db,"dragon_projection_relocation"):return None
    return db.execute("SELECT * FROM dragon_projection_relocation WHERE kind=?",(kind,)).fetchone()


def _binding(row,target):
    stat=target.stat()
    if (row["target"],row["device"],row["inode"])!=(str(target),stat.st_dev,stat.st_ino):
        raise DeploymentHeld("projection root binding differs")


def permit(db,kind,target):
    """Never use a former root after a relocation marker has been published."""
    row=_row(db,kind)
    if row is None:return
    _binding(row,target)
    if row["phase"]!="rebuilding":raise DeploymentHeld("projection enrollment rotation pending")


def begin(graph,kind,target,*,offline_acknowledged=False):
    _ack(offline_acknowledged);_kind(kind)
    target=_dir(Path(target));st=target.stat()
    # A new root must not contain any existing projection files. The one
    # operation may be retried against the exact same bound directory.
    from core.dragon_graph_authority import active
    with graph._db() as db:
        if active(db):raise DeploymentHeld("canonical graph has no derived graph projection")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute(SCHEMA)
            prior=_row(db,kind)
            if prior and prior["target"]==str(target):
                _binding(prior,target)
                db.execute("COMMIT")
                return {"operation":prior["operation"],"phase":prior["phase"],"replayed":True}
            if prior and prior["phase"]=="resetting":raise DeploymentHeld("finish previous enrollment rotation")
            with os.scandir(target) as entries:
                if next(entries,None) is not None:raise DeploymentHeld("new projection destination must be empty")
            op=secrets.token_hex(32)
            db.execute("""INSERT INTO dragon_projection_relocation VALUES(?,?,?,?,?,'',0,'resetting')
                ON CONFLICT(kind) DO UPDATE SET operation=excluded.operation,target=excluded.target,
                device=excluded.device,inode=excluded.inode,cursor='',owners=0,phase='resetting'""",
                       (kind,op,str(target),st.st_dev,st.st_ino))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"operation":op,"phase":"resetting","replayed":False,"old_projection_files_retained":True}


def advance(graph,kind,target,*,limit=LIMIT):
    """Rotate at most 32 existing owner epochs in one source transaction."""
    enrollment,versions,dirty,_=_kind(kind)
    if type(limit) is not int or not 1<=limit<=LIMIT:raise ValueError("rotation bound")
    target=_dir(Path(target))
    with graph._db() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            job=_row(db,kind)
            if job is None:
                db.execute("COMMIT");return None
            _binding(job,target)
            if job["phase"]=="rebuilding":
                db.execute("COMMIT");return None
            rows=db.execute("SELECT owner,epoch FROM "+enrollment+" WHERE owner>? ORDER BY owner LIMIT ?",
                            (job["cursor"],limit+1)).fetchall()
            page=rows[:limit];cursor=job["cursor"]
            for owner,old in page:
                if not isinstance(owner,str) or not HEX.fullmatch(owner) or not isinstance(old,str) or not HEX.fullmatch(old):
                    raise DeploymentHeld("projection owner/epoch differs")
                if not db.execute("SELECT 1 FROM lead_owner WHERE owner=?",(owner,)).fetchone():
                    raise DeploymentHeld("projection owner unavailable")
                epoch=secrets.token_hex(32)
                db.execute("DELETE FROM "+dirty+" WHERE owner=?",(owner,))
                db.execute("DELETE FROM "+versions+" WHERE owner=?",(owner,))
                db.executemany("INSERT INTO "+versions+" VALUES(?,?,0,?,0)",((owner,i,secrets.token_hex(32)) for i in range(LANES)))
                if db.execute("UPDATE "+enrollment+" SET epoch=?,next_lane=0,due=0 WHERE owner=? AND epoch=?",(epoch,owner,old)).rowcount!=1:
                    raise DeploymentHeld("projection enrollment changed")
                cursor=owner
            phase="rebuilding" if len(rows)<=limit else "resetting"
            db.execute("UPDATE dragon_projection_relocation SET cursor=?,owners=owners+?,phase=? WHERE kind=?",
                       (cursor,len(page),phase,kind))
            db.execute("COMMIT")
            return {"operation":job["operation"],"phase":phase,"owners_rotated":len(page),
                    "owners_rotated_total":job["owners"]+len(page),"canonical_search_available":True,
                    "projection_ready":False,"network_authorized":False}
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise


def status(graph,kind):
    _kind(kind)
    with graph._db() as db:
        value=_row(db,kind)
        if not value:return {"configured":False}
        return {"configured":True,"operation":value["operation"],"phase":value["phase"],
                "owners_rotated":value["owners"],"canonical_search_available":True,
                "coverage_verified":False}


def _hash_rows(rows):
    h=hashlib.sha256();n=0
    for row in rows:
        raw=json.dumps(list(row),ensure_ascii=True,separators=(",",":")).encode()
        h.update(len(raw).to_bytes(8,"big"));h.update(raw);n+=1
    return n,h.hexdigest()


def audit(graph,kind,scope):
    """Exact full owner projection witness, not just revision/counter equality.

    A bounded number of connections and streaming rows are used, but work is
    proportional to the selected owner's graph. Run outside request workers.
    """
    enrollment,versions,_,_=_kind(kind);owner=owner_key(scope);target=_target(kind)
    if kind=="nodes":
        from core.dragon_lead_index_shards import FIELDS,_shard,_identity
        open_lane=_shard;source_table="lead_nodes";projected="nodes"
    else:
        from core.dragon_lead_edge_shards import FIELDS,_file,_identity
        open_lane=_file;source_table="lead_edges";projected="edges"
    cols=",".join(FIELDS);results=[]
    with graph._db() as source:
        source.execute("BEGIN")
        try:
            permit(source,kind,target)
            row=source.execute("SELECT epoch FROM "+enrollment+" WHERE owner=?",(owner,)).fetchone()
            if not row:raise LookupError("owner not enrolled")
            epoch=row[0]
            for i in range(LANES):
                low,high=bounds(i)
                version=source.execute("SELECT revision,stamp FROM "+versions+" WHERE owner=? AND lane=?",(owner,i)).fetchone()
                if not version:raise DeploymentHeld("source revision absent")
                canonical=_hash_rows(source.execute("SELECT "+cols+" FROM "+source_table+" WHERE owner=? AND id>=? AND id<? ORDER BY id",(owner,low,high)))
                with open_lane(owner,epoch,i) as part:
                    part.execute("BEGIN")
                    try:
                        marker=_identity(part,owner,epoch,i)
                        if not marker or marker["phase"]!="catchup" or (marker["revision"],marker["stamp"])!=tuple(version):
                            raise DeploymentHeld("projection not caught up")
                        if [r[0] for r in part.execute("PRAGMA quick_check")]!=["ok"]:
                            raise DeploymentHeld("projection SQLite integrity differs")
                        actual=_hash_rows(part.execute("SELECT "+cols+" FROM "+projected+" ORDER BY id"))
                        if actual!=canonical:raise DeploymentHeld("projection canonical row witness differs")
                        if kind=="nodes":
                            expected=_hash_rows(part.execute("SELECT owner,id,title,url,kind,family FROM nodes ORDER BY id"))
                            fts=_hash_rows(part.execute("SELECT owner,id,title,url,kind,family FROM search ORDER BY id"))
                            if expected!=fts or part.execute("""SELECT 1 FROM nodes n LEFT JOIN search f ON f.rowid=n.fts_row
                                  WHERE f.rowid IS NULL OR f.owner IS NOT n.owner OR f.id IS NOT n.id OR f.title IS NOT n.title
                                  OR f.url IS NOT n.url OR f.kind IS NOT n.kind OR f.family IS NOT n.family LIMIT 1""").fetchone():
                                raise DeploymentHeld("projection FTS witness differs")
                        part.execute("COMMIT")
                    except BaseException:
                        if part.in_transaction:part.execute("ROLLBACK")
                        raise
                results.append({"lane":i,"rows":canonical[0],"sha256":canonical[1],"revision":version[0]})
            source.execute("COMMIT")
        except BaseException:
            if source.in_transaction:source.execute("ROLLBACK")
            raise
    return {"kind":kind,"owner":owner,"epoch":epoch,"rows":sum(r["rows"] for r in results),
            "lanes":results,"coverage_verified":True,"network_authorized":False}


def main():
    from core.dragon_lead_graph import LeadGraph
    from core.dragon_graph_deployment import _read_json
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    for cmd in ("begin","advance","status","audit"):
        a=sub.add_parser(cmd);a.add_argument("--corpus",required=True);a.add_argument("--kind",choices=tuple(KINDS),required=True)
        if cmd=="begin":
            a.add_argument("--target",required=True);a.add_argument("--offline-writers-stopped",action="store_true")
        if cmd=="audit":a.add_argument("--scope-json",required=True)
    a=p.parse_args();graph=LeadGraph(Path(a.corpus))
    if a.command=="begin":result=begin(graph,a.kind,a.target,offline_acknowledged=a.offline_writers_stopped)
    elif a.command=="advance":result=advance(graph,a.kind,_target(a.kind))
    elif a.command=="status":result=status(graph,a.kind)
    else:result=audit(graph,a.kind,_read_json(Path(a.scope_json)))
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":main()
